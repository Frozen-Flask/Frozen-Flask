"""
    flask_frozen
    ~~~~~~~~~~~~

    Frozen-Flask freezes a Flask application into a set of static files.
    The result can be hosted without any server-side software other than a
    traditional web server.


    :copyright: (c) 2010-2012 by Simon Sapin.
    :license: BSD, see LICENSE for more details.

"""

__all__ = ['Freezer', 'walk_directory', 'relative_url_for']

VERSION = '0.18'

import datetime
import os.path
import mimetypes
import warnings
import collections
import posixpath
from fnmatch import fnmatch
from unicodedata import normalize
from threading import Lock
from contextlib import contextmanager
from posixpath import relpath as posix_relpath

from collections import namedtuple
try:
    from collections.abc import Mapping  # Python 3
except ImportError:
    from collections import Mapping  # Python 2.7

try:
    from urlparse import urlsplit
    from werkzeug.urls import url_unquote as unquote
except ImportError:  # Python 3
    from urllib.parse import urlsplit, unquote

from werkzeug.exceptions import HTTPException
from flask import (Flask, Blueprint, url_for, request, send_from_directory,
                   redirect)

try:
    unicode
except NameError:  # Python 3
    unicode = str
    basestring = str


class FrozenFlaskWarning(Warning):
    pass


class MissingURLGeneratorWarning(FrozenFlaskWarning):
    pass


class MimetypeMismatchWarning(FrozenFlaskWarning):
    pass


class NotFoundWarning(FrozenFlaskWarning):
    pass


class RedirectWarning(FrozenFlaskWarning):
    pass


Page = namedtuple('Page', 'url path')


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
            self.url_for_logger = UrlForLogger(app)
            app.config.setdefault('FREEZER_DESTINATION', 'build')
            app.config.setdefault('FREEZER_DESTINATION_IGNORE', [])
            app.config.setdefault('FREEZER_STATIC_IGNORE', [])
            app.config.setdefault('FREEZER_BASE_URL', None)
            app.config.setdefault('FREEZER_REMOVE_EXTRA_FILES', True)
            app.config.setdefault('FREEZER_DEFAULT_MIMETYPE',
                                  'application/octet-stream')
            app.config.setdefault('FREEZER_IGNORE_MIMETYPE_WARNINGS', False)
            app.config.setdefault('FREEZER_RELATIVE_URLS', False)
            app.config.setdefault('FREEZER_IGNORE_404_NOT_FOUND', False)
            app.config.setdefault('FREEZER_REDIRECT_POLICY', 'follow')
            app.config.setdefault('FREEZER_SKIP_EXISTING', False)

    def register_generator(self, function):
        """
        Register a function as an URL generator.

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
        """
        Absolute path to the directory Frozen-Flask writes to,
        ie. resolved value for the ``FREEZER_DESTINATION`` configuration_.
        """
        # unicode() will raise if the path is not ASCII or already unicode.
        return os.path.join(
            unicode(self.app.root_path),
            unicode(self.app.config['FREEZER_DESTINATION'])
        )

    def freeze_yield(self):
        """Like :meth:`freeze`, but yields information about pages as they are
        being processed. Yields :func:`namedtuples <collections.namedtuple>`
        ``(url, path)``. This can be used to display progress information,
        such as printing the information to standard output, or even more
        sophisticated, e.g. with a :func:`progressbar <click.progressbar>`::

            import click

            with click.progressbar(
                    freezer.freeze_yield(),
                    item_show_func=lambda p: p.url if p else 'Done!') as urls:
                for url in urls:
                    # everything is already happening, just pass
                    pass
        """
        remove_extra = self.app.config['FREEZER_REMOVE_EXTRA_FILES']
        if not os.path.isdir(self.root):
            os.makedirs(self.root)
        if remove_extra:
            ignore = self.app.config['FREEZER_DESTINATION_IGNORE']
            previous_files = set(
                # See https://github.com/SimonSapin/Frozen-Flask/issues/5
                normalize('NFC', os.path.join(self.root, *name.split('/')))
                for name in walk_directory(self.root, ignore=ignore))
        seen_urls = set()
        seen_endpoints = set()
        built_files = set()

        for url, endpoint, last_modified in self._generate_all_urls():
            seen_endpoints.add(endpoint)
            if url in seen_urls:
                # Don't build the same URL more than once
                continue
            seen_urls.add(url)
            new_filename = self._build_one(url, last_modified)
            built_files.add(normalize('NFC', new_filename))
            yield Page(url, os.path.relpath(new_filename, self.root))

        self._check_endpoints(seen_endpoints)
        if remove_extra:
            # Remove files from the previous build that are not here anymore.
            for extra_file in previous_files - built_files:
                os.remove(extra_file)
                parent = os.path.dirname(extra_file)
                if not os.listdir(parent):
                    # The directory is now empty, remove it.
                    os.removedirs(parent)

    def freeze(self):
        """Clean the destination and build all URLs from generators."""
        return set(page.url for page in self.freeze_yield())

    def all_urls(self):
        """
        Run all generators and yield URLs relative to the app root.
        May be useful for testing URL generators.

        .. note::
            This does not generate any page, so URLs that are normally
            generated from :func:`~flask.url_for` calls will not be included
            here.
        """
        for url, _endpoint, last_modified in self._generate_all_urls():
            yield url

    def _script_name(self):
        """
        Return the path part of FREEZER_BASE_URL, without trailing slash.
        """
        base_url = self.app.config['FREEZER_BASE_URL']
        return urlsplit(base_url or '').path.rstrip('/')

    def _generate_all_urls(self):
        """
        Run all generators and yield (url, endpoint) tuples.
        """
        script_name = self._script_name()
        url_encoding = self.app.url_map.charset
        url_generators = list(self.url_generators)
        url_generators += [self.url_for_logger.iter_calls]
        # A request context is required to use url_for
        with self.app.test_request_context(base_url=script_name or None):
            for generator in url_generators:
                for generated in generator():
                    if isinstance(generated, basestring):
                        url = generated
                        endpoint = None
                        last_modified = None
                    else:
                        if isinstance(generated, Mapping):
                            values = generated
                            # The endpoint defaults to the name of the
                            # generator function, just like with Flask views.
                            endpoint = generator.__name__
                            last_modified = None
                        else:
                            # Assume a tuple.
                            if len(generated)==2:
                                endpoint, values = generated
                                last_modified = None
                            else:
                                endpoint, values, last_modified = generated
                        url = url_for(endpoint, **values)
                        assert url.startswith(script_name), (
                            'url_for returned an URL %r not starting with '
                            'script_name %r. Bug in Werkzeug?'
                            % (url, script_name)
                        )
                        url = url[len(script_name):]
                    # flask.url_for "quotes" URLs, eg. a space becomes %20
                    url = unquote(url)
                    parsed_url = urlsplit(url)
                    if parsed_url.scheme or parsed_url.netloc:
                        raise ValueError('External URLs not supported: ' + url)

                    # Remove any query string and fragment:
                    url = parsed_url.path
                    if not isinstance(url, unicode):
                        url = url.decode(url_encoding)
                    yield url, endpoint, last_modified

    def _check_endpoints(self, seen_endpoints):
        """
        Warn if some of the app's endpoints are not in seen_endpoints.
        """
        get_endpoints = set(
            rule.endpoint for rule in self.app.url_map.iter_rules()
            if 'GET' in rule.methods)
        not_generated_endpoints = get_endpoints - seen_endpoints

        if self.static_files_urls in self.url_generators:
            # Special case: do not warn when there is no static file
            not_generated_endpoints -= set(self._static_rules_endpoints())

        if not_generated_endpoints:
            warnings.warn(
                'Nothing frozen for endpoints %s. Did you forget a URL '
                'generator?' % ', '.join(
                    unicode(e) for e in not_generated_endpoints),
                MissingURLGeneratorWarning,
                stacklevel=3)

    def _build_one(self, url, last_modified=None):
        """Get the given ``url`` from the app and write the matching file."""
        client = self.app.test_client()
        base_url = self.app.config['FREEZER_BASE_URL']
        redirect_policy = self.app.config['FREEZER_REDIRECT_POLICY']
        follow_redirects = redirect_policy == 'follow'
        ignore_redirect = redirect_policy == 'ignore'

        destination_path = self.urlpath_to_filepath(url)
        filename = os.path.join(self.root, *destination_path.split('/'))

        skip = self.app.config['FREEZER_SKIP_EXISTING']
        if callable(skip):
            skip = skip(url, filename)
        if os.path.isfile(filename):
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(filename))
            if (last_modified is not None and mtime>=last_modified) or skip:
                return filename

        with conditional_context(self.url_for_logger, self.log_url_for):
            with conditional_context(patch_url_for(self.app),
                                     self.app.config['FREEZER_RELATIVE_URLS']):
                response = client.get(url, follow_redirects=follow_redirects,
                                      base_url=base_url)

        # The client follows redirects by itself
        # Any other status code is probably an error
        # except we explicitly want 404 errors to be skipped
        # (eg. while application is in development)
        ignore_404 = self.app.config['FREEZER_IGNORE_404_NOT_FOUND']
        if response.status_code != 200:
            if response.status_code == 404 and ignore_404:
                warnings.warn('Ignored %r on URL %s' % (response.status, url),
                              NotFoundWarning,
                              stacklevel=3)
            elif response.status_code in (301, 302) and ignore_redirect:
                warnings.warn('Ignored %r on URL %s' % (response.status, url),
                              RedirectWarning,
                              stacklevel=3)
            else:
                raise ValueError('Unexpected status %r on URL %s' \
                    % (response.status, url))

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

        response.close()
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
        """
        Run an HTTP server on the result of the build.

        :param options: passed to :meth:`flask.Flask.run`.
        """
        app = self.make_static_app()
        script_name = self._script_name()
        app.wsgi_app = script_name_middleware(app.wsgi_app, script_name)
        app.run(**options)

    def run(self, **options):
        """Same as :meth:`serve` but calls :meth:`freeze` before serving."""
        self.freeze()
        self.serve(**options)

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
            # Flask has historically always used the literal string 'static' to
            # refer to the static file serving endpoint.  Arguably this could
            # be considered fragile; equally it is unlikely to change.  See
            # https://github.com/pallets/flask/discussions/4136 for some
            # related discussion.
            elif rule.endpoint == 'static':
                yield rule.endpoint

    def static_files_urls(self):
        """
        URL generator for static files for app and all registered blueprints.
        """
        for endpoint in self._static_rules_endpoints():
            view = self.app.view_functions[endpoint]
            app_or_blueprint = method_self(view) or self.app
            root = app_or_blueprint.static_folder
            ignore = self.app.config['FREEZER_STATIC_IGNORE']
            if root is None or not os.path.isdir(root):
                # No 'static' directory for this app/blueprint.
                continue
            for filename in walk_directory(root, ignore=ignore):
                yield endpoint, {'filename': filename}

    def no_argument_rules_urls(self):
        """URL generator for URL rules that take no arguments."""
        for rule in self.app.url_map.iter_rules():
            if not rule.arguments and 'GET' in rule.methods:
                yield rule.endpoint, {}


def walk_directory(root, ignore=()):
    """
    Recursively walk the `root` directory and yield slash-separated paths
    relative to the root.

    Used to implement the URL generator for static files.

    :param ignore:
        A list of :mod:`fnmatch` patterns.
        As in ``.gitignore`` files,
        patterns that contain a slash are matched against the whole path,
        others against individual slash-separated parts.

    """
    path_ignore = [n.strip('/') for n in ignore if '/' in n]
    basename_ignore = [n for n in ignore if '/'  not in n]

    def walk(directory, path_so_far):
        for name in sorted(os.listdir(directory)):
            if any(fnmatch(name, pattern) for pattern in basename_ignore):
                continue
            path = path_so_far + '/' + name if path_so_far else name
            if any(fnmatch(path, pattern) for pattern in path_ignore):
                continue
            full_name = os.path.join(directory, name)
            if os.path.isdir(full_name):
                for file_path in walk(full_name, path):
                    yield file_path
            elif os.path.isfile(full_name):
                yield path
    return walk(root, '')


@contextmanager
def patch_url_for(app):
    """
    Patches ``url_for`` in Jinja globals to use :func:`relative_url_for`.

    This is a context manager, to be used in a ``with`` statement.
    """
    previous_url_for = app.jinja_env.globals['url_for']
    app.jinja_env.globals['url_for'] = relative_url_for
    try:
        yield
    finally:
        app.jinja_env.globals['url_for'] = previous_url_for


def relative_url_for(endpoint, **values):
    """
    Like :func:`~flask.url_for`, but returns relative URLs if possible.

    Absolute URLs (with ``_external=True`` or to a different subdomain) are
    unchanged, but eg. ``/foo/bar`` becomes ``../bar``, depending on the
    current request context's path. (This, of course, requires a Flask
    :ref:`request context <flask:request-context>`.)

    URLs that would otherwise end with ``/`` get ``index.html`` appended,
    as Frozen-Flask does in filenames. Because of this behavior, this function
    should only be used with Frozen-Flask, not when running the application in
    :meth:`app.run() <flask.Flask.run>` or another WSGI sever.

    If the ``FREEZER_RELATIVE_URLS`` `configuration`_ is True, Frozen-Flask
    will automatically patch the application's Jinja environment so that
    ``url_for`` in templates is this function.
    """
    url = url_for(endpoint, **values)

    # absolute URLs in http://... (with subdomains or _external=True)
    if not url.startswith('/'):
        return url

    url, fragment_sep, fragment = url.partition('#')
    url, query_sep, query = url.partition('?')
    if url.endswith('/'):
        url += 'index.html'
    url += query_sep + query + fragment_sep + fragment

    request_path = request.path
    if not request_path.endswith('/'):
        request_path = posixpath.dirname(request_path)

    return posix_relpath(url, request_path)


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
        try:
            # Python 3
            return method.__self__
        except AttributeError:
            # Not a method.
            return


@contextmanager
def conditional_context(context, condition):
    """Wrap a context manager but only enter/exit it if condition is true."""
    if condition:
        with context:
            yield
    else:
        yield


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
