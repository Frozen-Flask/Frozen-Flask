"""
    flaskext.frozen
    ~~~~~~~~~~~~~~~

    Frozen-Flask freezes a Flask application into a set of static files.
    The result can be hosted without any server-side software other than a
    traditional web server.


    :copyright: (c) 2010 by Simon Sapin.
    :license: BSD, see LICENSE for more details.
"""

from __future__ import with_statement

import os.path
import mimetypes
import urlparse
import urllib
import warnings
import collections
from unicodedata import normalize
from threading import Lock

from werkzeug.exceptions import HTTPException
from flask import (Flask, Blueprint, url_for, request, send_from_directory,
                   redirect)

try:
    from collections import Mapping
    def is_mapping(obj):
        return isinstance(obj, Mapping)
except ImportError:
    # Python 2.5, no Abstract Base Classes. Default to duck-typing.
    def is_mapping(obj):
        return hasattr(obj, 'keys')


__all__ = ['Freezer']

VERSION = '0.8'


class MissingURLGeneratorWarning(Warning):
    pass


class MimetypeMismatchWarning(Warning):
    pass


class Freezer(object):
    """
    :param app: your application or None if you use :meth:`init_app`
    :type app: Flask instance

    :param with_static_files: Whether to automatically generate URLs
                              for static files.
    :type with_static_files: boolean

    :param with_no_argument_rules: Whether to automatically generate URLs
                                   for URL rules that take no arguments.
    :type with_no_argument_rules: boolean

    :param log_url_for: Whether to log calls your app makes to
                        :func:`~flask.url_for` and generate URLs from that.

                        .. versionadded:: 0.6
    :type log_url_for: boolean
    """
    def __init__(self, app=None, with_static_files=True,
                 with_no_argument_rules=True, log_url_for=True):
        self.url_generators = []
        self.log_url_for = log_url_for
        if with_static_files:
            self.register_generator(self.static_files_urls)
        if with_no_argument_rules:
            self.register_generator(self.no_argument_rules_urls)
        self.init_app(app)

    def init_app(self, app):
        """
        Allow to register an app after the Freezer initialization.

        :param app: your Flask application
        """
        self.app = app
        if app:
            logger_class = (UrlForLogger if self.log_url_for
                            else DummyUrlForLogger)
            self.url_for_logger = logger_class(app)
            app.config.setdefault('FREEZER_DESTINATION', 'build')
            app.config.setdefault('FREEZER_BASE_URL', 'http://localhost/')
            app.config.setdefault('FREEZER_REMOVE_EXTRA_FILES', True)
            app.config.setdefault('FREEZER_DEFAULT_MIMETYPE',
                                  'application/octet-stream')
            app.config.setdefault('FREEZER_IGNORE_MIMETYPE_WARNINGS', False)

    def register_generator(self, function):
        """Register a function as an URL generator.

        The function should return an iterable of URL paths or
        ``(endpoint, values)`` tuples to be used as
        ``url_for(endpoint, **values)``.

        :Returns: the function, so that it can be used as a decorator
        """
        self.url_generators.append(function)
        # Allow use as a decorator
        return function

    @property
    def root(self):
        """The build destination."""
        # unicode() will raise if the path is not ASCII or already unicode.
        return os.path.join(
            unicode(self.app.root_path),
            unicode(self.app.config['FREEZER_DESTINATION'])
        )

    def freeze(self):
        """Clean the destination and build all URLs from generators."""
        remove_extra = self.app.config['FREEZER_REMOVE_EXTRA_FILES']
        if not os.path.isdir(self.root):
            os.makedirs(self.root)
        previous_files = set(
            # See https://github.com/SimonSapin/Frozen-Flask/issues/5
            normalize('NFC', os.path.join(self.root, *name.split('/')))
            for name in walk_directory(self.root)
        )
        seen_urls = set()
        seen_endpoints = set()
        built_files = set()
        for url, endpoint in self._generate_all_urls():
            seen_endpoints.add(endpoint)
            if url in seen_urls:
                # Don't build the same URL more than once
                continue
            seen_urls.add(url)
            new_filename = self._build_one(url)
            built_files.add(normalize('NFC', new_filename))
        self._check_endpoints(seen_endpoints)
        if remove_extra:
            # Remove files from the previous build that are not here anymore.
            for extra_file in previous_files - built_files:
                os.remove(extra_file)
                parent = os.path.dirname(extra_file)
                if not os.listdir(parent):
                    # The directory is now empty, remove it.
                    os.removedirs(parent)
        return seen_urls

    def all_urls(self):
        """
        Run all generators and yield URLs relative to the app root.
        May be useful for testing URL generators.

        .. note::
            This does not generate any page, so URLs that are normally
            generated from :func:`~flask.url_for` calls will not be included
            here.
        """
        for url, _endpoint in self._generate_all_urls():
            yield url

    def _script_name(self):
        """
        Return the path part of FREEZER_BASE_URL, without trailing slash.
        """
        base_url = self.app.config['FREEZER_BASE_URL']
        return urlparse.urlsplit(base_url).path.rstrip('/')

    def _generate_all_urls(self):
        """
        Run all generators and yield (url, enpoint) tuples.
        """
        script_name = self._script_name()
        url_encoding = self.app.url_map.charset
        url_generators = list(self.url_generators)
        url_generators += [self.url_for_logger.iter_calls]
        # A request context is required to use url_for
        with self.app.test_request_context(base_url=script_name):
            for generator in url_generators:
                for generated in generator():
                    if isinstance(generated, basestring):
                        url = generated
                        endpoint = None
                    else:
                        if is_mapping(generated):
                            values = generated
                            # The endpoint defaults to the name of the
                            # generator function, just like with Flask views.
                            endpoint = generator.__name__
                        else:
                            # Assume a tuple.
                            endpoint, values = generated
                        url = url_for(endpoint, **values)
                        assert url.startswith(script_name), (
                            'url_for returned an URL %r not starting with '
                            'script_name %r. Bug in Werkzeug?'
                            % (url, script_name)
                        )
                        url = url[len(script_name):]
                    # flask.url_for "quotes" URLs, eg. a space becomes %20
                    url = urllib.unquote(url)
                    parsed_url = urlparse.urlsplit(url)
                    if parsed_url.scheme or parsed_url.netloc:
                        raise ValueError('External URLs not supported: ' + url)

                    # Remove any query string and fragment:
                    url = parsed_url.path
                    if not isinstance(url, unicode):
                        url = url.decode(url_encoding)
                    yield url, endpoint

    def _check_endpoints(self, seen_endpoints):
        """
        Warn if some of the app's enpoints are not in seen_endpoints.
        """
        all_endpoints = set(
            rule.endpoint for rule in self.app.url_map.iter_rules())
        not_generated_endpoints = all_endpoints - seen_endpoints

        if self.static_files_urls in self.url_generators:
            # Special case: do not warn when there is no static file
            not_generated_endpoints -= set(self._static_rules_endpoints())

        if not_generated_endpoints:
            warnings.warn(
                'Nothing frozen for endpoints %s. Did you forget an URL '
                'generator?' % ', '.join(
                    unicode(e) for e in not_generated_endpoints),
                MissingURLGeneratorWarning,
                stacklevel=3)

    def _build_one(self, url):
        """Get the given ``url`` from the app and write the matching file.
        """
        client = self.app.test_client()
        base_url = self.app.config['FREEZER_BASE_URL']

        with self.url_for_logger:
            response = client.get(url, follow_redirects=True,
                                  base_url=base_url)

        # The client follows redirects by itself
        # Any other status code is probably an error
        if not(response.status_code == 200):
            raise ValueError('Unexpected status %r on URL %s' \
                % (response.status, url))

        destination_path = self.urlpath_to_filepath(url)
        filename = os.path.join(self.root, *destination_path.split('/'))

        if not self.app.config['FREEZER_IGNORE_MIMETYPE_WARNINGS']:
            # Most web servers guess the mime type of static files by their
            # filename.  Check that this guess is consistent with the actual
            # Content-Type header we got from the app.
            basename = os.path.basename(filename)
            guessed_type, guessed_encoding = mimetypes.guess_type(basename)
            if not guessed_type:
                # Used by most server when they can not determine the type
                guessed_type = self.app.config['FREEZER_DEFAULT_MIMETYPE']

            if not guessed_type == response.mimetype:
                warnings.warn(
                    'Filename extension of %r (type %s) does not match Content-'
                    'Type: %s' % (basename, guessed_type, response.content_type),
                    MimetypeMismatchWarning,
                    stacklevel=3)

        # Create directories as needed
        dirname = os.path.dirname(filename)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

        # Write the file, but only if its content has changed
        content = response.data
        if os.path.isfile(filename):
            with open(filename, 'rb') as fd:
                previous_content = fd.read()
        else:
            previous_content = None
        if content != previous_content:
            # Do not overwrite when content hasn't changed to help rsync
            # by keeping the modification date.
            with open(filename, 'wb') as fd:
                fd.write(content)

        return filename

    def urlpath_to_filepath(self, path):
        """
        Convert a URL path like /admin/ to a file path like admin/index.html
        """
        if path.endswith('/'):
            path += 'index.html'
        # Remove the initial slash that should always be there
        assert path.startswith('/')
        return path[1:]

    def serve(self, **options):
        """Run an HTTP server on the result of the build.

        :param options: passed to ``app.run()``.
        """
        app = self.make_static_app()
        script_name = self._script_name()
        app.wsgi_app = script_name_middleware(app.wsgi_app, script_name)
        app.run(**options)

    def make_static_app(self):
        """Return a Flask application serving the build destination."""
        root = os.path.join(
            self.app.root_path,
            self.app.config['FREEZER_DESTINATION']
        )

        def dispatch_request():
            filename = self.urlpath_to_filepath(request.path)

            # Override the default mimeype from settings
            guessed_type, guessed_encoding = mimetypes.guess_type(filename)
            if not guessed_type:
                guessed_type = self.app.config['FREEZER_DEFAULT_MIMETYPE']

            return send_from_directory(root, filename, mimetype=guessed_type)

        app = Flask(__name__)
        # Do not use the URL map
        app.dispatch_request = dispatch_request
        return app

    def _static_rules_endpoints(self):
        """
        Yield the 'static' URL rules for the app and all blueprints.
        """
        send_static_file = unwrap_method(Flask.send_static_file)
        # Assumption about a Flask internal detail:
        # Flask and Blueprint inherit the same method.
        # This will break loudly if the assumption isn't valid anymore in
        # a future version of Flask
        assert unwrap_method(Blueprint.send_static_file) is send_static_file

        for rule in self.app.url_map.iter_rules():
            view = self.app.view_functions[rule.endpoint]
            if unwrap_method(view) is send_static_file:
                yield rule.endpoint

    def static_files_urls(self):
        """
        URL generator for static files for app and all registered blueprints.
        """
        for endpoint in self._static_rules_endpoints():
            view = self.app.view_functions[endpoint]
            app_or_blueprint = method_self(view)
            root = app_or_blueprint.static_folder
            if root is None or not os.path.isdir(root):
                # No 'static' directory for this app/blueprint.
                continue
            for filename in walk_directory(root):
                yield endpoint, {'filename': filename}

    def no_argument_rules_urls(self):
        """URL generator for URL rules that take no arguments."""
        for rule in self.app.url_map.iter_rules():
            if not rule.arguments:
                yield rule.endpoint, {}


def walk_directory(root):
    """
    Recursively walk the `root` directory and yield slash-separated paths
    relative to the root.

    Used to implement the URL genertor for static files.
    """
    for name in os.listdir(root):
        full_name = os.path.join(root, name)
        if os.path.isdir(full_name):
            for filename in walk_directory(full_name):
                yield name + '/' + filename
        elif os.path.isfile(full_name):
            yield name


def unwrap_method(method):
    """Return the function object for the given method object."""
    try:
        # Python 2
        return method.im_func
    except AttributeError:
        try:
            # Python 3
            return method.__func__
        except AttributeError:
            # Not a method.
            return method


def method_self(method):
    """Return the instance a bound method is attached to."""
    try:
        # Python 2
        return method.im_self
    except AttributeError:
        # Python 3
        return method.__self__


class UrlForLogger(object):
    """
    Log all calls to url_for() for this app made inside the with block.

    Use this object as a context manager in a with block to enable logging.
    """

    def __init__(self, app):
        self.app = app
        self.logged_calls = collections.deque()
        self._enabled = False
        self._lock = Lock()

        def logger(endpoint, values):
            # Make a copy of values as other @app.url_defaults functions are
            # meant to mutate this dict.
            if self._enabled:
                self.logged_calls.append((endpoint, values.copy()))

        # Do not use app.url_defaults() as we want to insert at the front
        # of the list to get unmodifies values.
        self.app.url_default_functions.setdefault(None, []).insert(0, logger)

    def __enter__(self):
        self._lock.acquire()
        self._enabled = True

    def __exit__(self, exc_type, exc_value, traceback):
        self._enabled = False
        self._lock.release()

    def iter_calls(self):
        """
        Return an iterable of (endpoint, values_dict) tuples, one for each
        call that was made while the logger was enabled.
        """
        # "Iterate" on the call deque while it is still being appended to.
        while self.logged_calls:
            yield self.logged_calls.popleft()


class DummyUrlForLogger(object):
    """
    Gives the same API as UrlForLogger, but does not actually log anything.
    """
    def __init__(self, app):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def iter_calls(self):
        return iter([])


def script_name_middleware(application, script_name):
    """
    Wrap a WSGI application in a middleware that moves ``script_name``
    from the environ's PATH_INFO to SCRIPT_NAME if it is there, and
    redirect to ``script_name`` otherwise.
    """
    def new_application(environ, start_response):
        path_info = environ['PATH_INFO']
        if path_info.startswith(script_name):
            environ['SCRIPT_NAME'] += script_name
            environ['PATH_INFO'] = path_info[len(script_name):]
            next = application
        else:
            next = redirect(script_name + '/')
        return next(environ, start_response)
    return new_application
