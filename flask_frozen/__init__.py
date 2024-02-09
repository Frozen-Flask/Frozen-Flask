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

import collections
import datetime
import mimetypes
import os
import posixpath
import warnings
from collections import namedtuple
from collections.abc import Mapping
from contextlib import contextmanager, suppress
from fnmatch import fnmatch
from pathlib import Path
from threading import Lock
from unicodedata import normalize
from urllib.parse import unquote, urlsplit

from flask import (Blueprint, Flask, redirect, request, send_from_directory,
                   url_for)

VERSION = '1.0.2'


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


class Freezer:
    """Flask app freezer.

    :param app: your application or None if you use :meth:`init_app`
    :type app: :class:`flask.Flask`

    :param bool with_static_files: Whether to automatically generate URLs for
        static files.

    :param bool with_no_argument_rules: Whether to automatically generate URLs
        for URL rules that take no arguments.

    :param bool log_url_for: Whether to log calls your app makes to
        :func:`flask.url_for` and generate URLs from that.

        .. versionadded:: 0.6
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
        """Allow to register an app after the Freezer initialization.

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
        """Absolute path to the directory Frozen-Flask writes to.

        Resolved value for the ``FREEZER_DESTINATION`` configuration_.
        """
        root = Path(self.app.root_path)
        return root / self.app.config['FREEZER_DESTINATION']

    def freeze_yield(self):
        """Like :meth:`freeze` but yields info while processing pages.

        Yields :func:`namedtuples <collections.namedtuple>`
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
        self.root.mkdir(parents=True, exist_ok=True)
        seen_urls = set()
        seen_endpoints = set()
        built_paths = set()

        for url, endpoint, last_modified in self._generate_all_urls():
            seen_endpoints.add(endpoint)
            if url in seen_urls:
                # Don't build the same URL more than once
                continue
            seen_urls.add(url)
            new_path = self._build_one(url, last_modified)
            built_paths.add(new_path)
            yield Page(url, new_path.relative_to(self.root))

        self._check_endpoints(seen_endpoints)
        if remove_extra:
            # Remove files from the previous build that are not here anymore.
            ignore = self.app.config['FREEZER_DESTINATION_IGNORE']
            previous_paths = set(
                Path(self.root / name) for name in
                walk_directory(self.root, ignore=ignore))
            for extra_path in previous_paths - built_paths:
                extra_path.unlink()
                with suppress(OSError):
                    extra_path.parent.rmdir()

    def freeze(self):
        """Clean the destination and build all URLs from generators."""
        return set(page.url for page in self.freeze_yield())

    def all_urls(self):
        """Run all generators and yield URLs relative to the app root.

        May be useful for testing URL generators.

        .. note::
            This does not generate any page, so URLs that are normally
            generated from :func:`flask.url_for` calls will not be included
            here.
        """
        for url, _, _ in self._generate_all_urls():
            yield url

    def _script_name(self):
        """Return the path part of FREEZER_BASE_URL, without trailing slash."""
        base_url = self.app.config['FREEZER_BASE_URL']
        return urlsplit(base_url or '').path.rstrip('/')

    def _generate_all_urls(self):
        """Run all generators and yield (url, endpoint) tuples."""
        script_name = self._script_name()
        # Charset is always set to UTF-8 since Werkzeug 2.3.0
        url_encoding = getattr(self.app.url_map, 'charset', 'utf-8')
        url_generators = list(self.url_generators)
        url_generators += [self.url_for_logger.iter_calls]
        # A request context is required to use url_for
        with self.app.test_request_context(base_url=script_name or None):
            for generator in url_generators:
                for generated in generator():
                    if isinstance(generated, str):
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
                            if len(generated) == 2:
                                endpoint, values = generated
                                last_modified = None
                            else:
                                endpoint, values, last_modified = generated
                        url = url_for(endpoint, **values)
                        assert url.startswith(script_name), (
                            f'url_for returned an URL {url} not starting with '
                            f'script_name {script_name!r}. Bug in Werkzeug?'
                        )
                        url = url[len(script_name):]
                    # flask.url_for "quotes" URLs, eg. a space becomes %20
                    url = unquote(url)
                    parsed_url = urlsplit(url)
                    if parsed_url.scheme or parsed_url.netloc:
                        raise ValueError(f'External URLs not supported: {url}')

                    # Remove any query string and fragment:
                    url = parsed_url.path
                    if not isinstance(url, str):
                        url = url.decode(url_encoding)
                    yield url, endpoint, last_modified

    def _check_endpoints(self, seen_endpoints):
        """Warn if some of the app's endpoints are not in seen_endpoints."""
        get_endpoints = set(
            rule.endpoint for rule in self.app.url_map.iter_rules()
            if 'GET' in rule.methods)
        not_generated_endpoints = get_endpoints - seen_endpoints

        if self.static_files_urls in self.url_generators:
            # Special case: do not warn when there is no static file
            not_generated_endpoints -= set(self._static_rules_endpoints())

        if not_generated_endpoints:
            endpoints = ', '.join(str(e) for e in not_generated_endpoints)
            warnings.warn(
                f'Nothing frozen for endpoints {endpoints}. '
                'Did you forget a URL generator?',
                MissingURLGeneratorWarning,
                stacklevel=3)

    def _build_one(self, url, last_modified=None):
        """Get the given ``url`` from the app and write the matching file."""
        client = self.app.test_client()
        base_url = self.app.config['FREEZER_BASE_URL']
        redirect_policy = self.app.config['FREEZER_REDIRECT_POLICY']
        follow_redirects = redirect_policy == 'follow'
        ignore_redirect = redirect_policy == 'ignore'

        destination_path = normalize('NFC', self.urlpath_to_filepath(url))
        path = self.root / destination_path

        skip = self.app.config['FREEZER_SKIP_EXISTING']
        if callable(skip):
            skip = skip(url, str(path))
        if path.is_file():
            mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
            if (last_modified is not None and mtime >= last_modified) or skip:
                return path

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
                warnings.warn(f'Ignored {response.status!r} on URL {url}',
                              NotFoundWarning,
                              stacklevel=3)
            elif response.status_code in (301, 302) and ignore_redirect:
                warnings.warn(f'Ignored {response.status!r} on URL {url}',
                              RedirectWarning,
                              stacklevel=3)
            else:
                raise ValueError(
                    f'Unexpected status {response.status!r} on URL {url}')

        if not self.app.config['FREEZER_IGNORE_MIMETYPE_WARNINGS']:
            # Most web servers guess the mime type of static files by their
            # filename.  Check that this guess is consistent with the actual
            # Content-Type header we got from the app.
            guessed_type, guessed_encoding = mimetypes.guess_type(path.name)
            if not guessed_type:
                # Used by most server when they can not determine the type
                guessed_type = self.app.config['FREEZER_DEFAULT_MIMETYPE']

            if not guessed_type == response.mimetype:
                warnings.warn(
                    f'Filename extension of {path.name!r} '
                    f'(type {guessed_type}) does not match '
                    f'Content-Type: {response.content_type}',
                    MimetypeMismatchWarning,
                    stacklevel=3)

        # Create directories as needed
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file, but only if its content has changed
        content = response.data
        previous_content = path.read_bytes() if path.is_file() else None
        if content != previous_content:
            # Do not overwrite when content hasn't changed to help rsync
            # by keeping the modification date.
            path.write_bytes(content)

        response.close()
        return path

    def urlpath_to_filepath(self, path):
        """Convert URL path like /admin/ to file path like admin/index.html."""
        if path.endswith('/'):
            path += 'index.html'
        # Remove the initial slash that should always be there
        assert path.startswith('/')
        return path[1:]

    def serve(self, **options):
        """Run an HTTP server on the result of the build.

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
        def dispatch_request():
            filename = self.urlpath_to_filepath(request.path)

            # Override the default mimeype from settings
            guessed_type, _ = mimetypes.guess_type(filename)
            if not guessed_type:
                guessed_type = self.app.config['FREEZER_DEFAULT_MIMETYPE']

            return send_from_directory(
                self.root, filename, mimetype=guessed_type)

        app = Flask(__name__)
        # Do not use the URL map
        app.dispatch_request = dispatch_request
        return app

    def _static_rules_endpoints(self):
        """Yield the 'static' URL rules for the app and all blueprints."""
        send_static_file_functions = (
            unwrap_method(Flask.send_static_file),
            unwrap_method(Blueprint.send_static_file))

        for rule in self.app.url_map.iter_rules():
            view = self.app.view_functions[rule.endpoint]
            if unwrap_method(view) in send_static_file_functions:
                yield rule.endpoint
            # Flask has historically always used the literal string 'static' to
            # refer to the static file serving endpoint.  Arguably this could
            # be considered fragile; equally it is unlikely to change.  See
            # https://github.com/pallets/flask/discussions/4136 for some
            # related discussion.
            elif rule.endpoint == 'static':
                yield rule.endpoint

    def static_files_urls(self):
        """URL generator for static files for app and all its blueprints."""
        for endpoint in self._static_rules_endpoints():
            view = self.app.view_functions[endpoint]
            app_or_blueprint = method_self(view) or self.app
            root = app_or_blueprint.static_folder
            ignore = self.app.config['FREEZER_STATIC_IGNORE']
            if root is None or not Path(root).is_dir():
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
    """Walk the `root` folder and yield slash-separated paths relative to root.

    Used to implement the URL generator for static files.

    :param ignore:
        A list of :mod:`fnmatch` patterns.
        As in ``.gitignore`` files,
        patterns that contain a slash are matched against the whole path,
        others against individual slash-separated parts.

    """
    for dir, dirs, filenames in os.walk(root):
        relative_dir = Path(dir).relative_to(root)
        dir_path = str(relative_dir)

        # Filter ignored directories
        patterns = [
            full_pattern for pattern in ignore for full_pattern in (
                pattern.rstrip('/'),
                f'{pattern}*',
                f'*/{pattern.rstrip("/")}',
                f'*/{pattern}*',
            )
        ]
        if any(fnmatch(dir_path, pattern) for pattern in patterns):
            continue

        # Filter ignored filenames
        for filename in filenames:
            path = str(relative_dir / filename)
            if os.sep != '/':
                path = path.replace(os.sep, '/')
            for pattern in ignore:
                if '/' in pattern.rstrip('/'):
                    if fnmatch(path, f'{pattern.lstrip("/")}*'):
                        break
                elif not pattern.endswith('/'):
                    if fnmatch(filename, pattern):
                        break
            else:
                # See https://github.com/SimonSapin/Frozen-Flask/issues/5
                yield normalize('NFC', path)


@contextmanager
def patch_url_for(app):
    """Patches ``url_for`` in Jinja globals to use :func:`relative_url_for`.

    This is a context manager, to be used in a ``with`` statement.
    """
    previous_url_for = app.jinja_env.globals['url_for']
    app.jinja_env.globals['url_for'] = relative_url_for
    try:
        yield
    finally:
        app.jinja_env.globals['url_for'] = previous_url_for


def relative_url_for(endpoint, **values):
    """Like :func:`flask.url_for`, but returns relative URLs if possible.

    Absolute URLs (with ``_external=True`` or to a different subdomain) are
    unchanged, but eg. ``/foo/bar`` becomes ``../bar``, depending on the
    current request context's path. (This, of course, requires a Flask
    :doc:`request context <flask:reqcontext>`.)

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

    return posixpath.relpath(url, request_path)


def unwrap_method(method):
    """Return the function object for the given method object."""
    return getattr(method, '__func__', method)


def method_self(method):
    """Return the instance a bound method is attached to."""
    return getattr(method, '__self__', None)


@contextmanager
def conditional_context(context, condition):
    """Wrap a context manager but only enter/exit it if condition is true."""
    if condition:
        with context:
            yield
    else:
        yield


class UrlForLogger:
    """Log all calls to url_for() for this app made inside the with block.

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
        # of the list to get unmodified values.
        self.app.url_default_functions.setdefault(None, []).insert(0, logger)

    def __enter__(self):
        self._lock.acquire()
        self._enabled = True

    def __exit__(self, exc_type, exc_value, traceback):
        self._enabled = False
        self._lock.release()

    def iter_calls(self):
        """Yield logged calls of endpoints.

        Return an iterable of (endpoint, values_dict) tuples, one for each call
        that was made while the logger was enabled.
        """
        # "Iterate" on the call deque while it is still being appended to.
        while self.logged_calls:
            yield self.logged_calls.popleft()


def script_name_middleware(application, script_name):
    """Wrap a WSGI app in a middleware to handle custom base URL.

    The middleware moves ``script_name`` from the environ's PATH_INFO to
    SCRIPT_NAME if it is there, and redirect to ``script_name`` otherwise.
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
