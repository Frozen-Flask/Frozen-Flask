"""
    flaskext.static
    ~~~~~~~~~~~~~~~

    Flask-Static builds a static snapshot of your Flask application. The
    result can be hosted without any server-side software other than a
    traditional web server.

    :copyright: (c) 2010 by Simon Sapin.
    :license: BSD, see LICENSE for more details.
"""

from __future__ import with_statement

import os.path
import mimetypes
import shutil

from werkzeug import Client
from werkzeug.exceptions import HTTPException
from flask import Flask, Module, url_for, request, send_from_directory


__all__ = ['StaticBuilder']


class StaticBuilder(object):
    """
    :param app: your application
    :type app: Flask instance
    :param with_static_files: Whether to automatically generate URLs
                              for static files.
    :type with_static_files boolean:
    :param with_no_argument_rules: Whether to automatically generate URLs
                                   for URL rules that take no arguments.
    :type with_no_argument_rules boolean:
    """
    def __init__(self, app, with_static_files=True,
                 with_no_argument_rules=True):
        app.config.setdefault('STATIC_BUILDER_DESTINATION', 'build')
        self.app = app
        self.url_generators = []
        if with_static_files:
            self.register_generator(self.static_files_urls)
        if with_no_argument_rules:
            self.register_generator(self.no_argument_rules_urls)
    
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
        return os.path.join(
            self.app.root_path,
            self.app.config['STATIC_BUILDER_DESTINATION']
        )
    
    def build(self):
        """Clean the destination and build all URLs from generators."""
        for name in os.listdir(self.root):
            shutil.rmtree(os.path.join(self.root, name))
        seen_urls = set()
        # A request context is required to use url_for
        with self.app.test_request_context():
            for generator in self.url_generators:
                for url in generator():
                    if not isinstance(url, basestring):
                        endpoint, values = url
                        url = url_for(endpoint, **values)
                    if url in seen_urls:
                        # Don't build the same URL more than once
                        continue
                    seen_urls.add(url)
                    self.build_one(url)
        return seen_urls

    def build_one(self, url):
        """Get the given ``url`` from the app and write the matching file.
        """
        client = self.app.test_client()
        response = client.get(url, follow_redirects=True)
        # The client follows redirects by itself
        # Any other status code is probably an error
        assert response.status_code == 200, 'Unexpected status %r on URL %s' \
            % (response.status, url)
        
        destination_path = url + 'index.html' if url.endswith('/') else url
        
        # Most web servers guess the mime type of static files by their
        # filename.  Check that this guess is consistent with the actual
        # Content-Type header we got from the app.
        basename = destination_path.rsplit('/', 1)[-1]
        guessed_type, guessed_encoding = mimetypes.guess_type(basename)
        if not guessed_type:
            # Used by most server when they can not determine the type
            guessed_type = 'application/octet-stream'
        assert guessed_type == response.mimetype, (
            'Filaname extension of %r (type %s) does not match Content-Type: %s'
            % (basename, guessed_type, response.content_type)
        )
        
        # Remove the initial slash that should always be there
        assert destination_path[0] == '/'
        destination_path = destination_path[1:]
        
        filename = os.path.join(self.root, *destination_path.split('/'))
        dirname = os.path.dirname(filename)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
        with open(filename, 'wb') as fd:
            # response.response is the original iterable return by the app
            # response is a convenience wrapper built by the test client
            for chunk in response.response:
                fd.write(chunk)
    
    def serve(self, **options):
        """Run an HTTP server on the result of the build.
        
        :param options: passed to ``app.run()``.
        """
        self.make_static_app().run(**options)

    def make_static_app(self):
        """Return a Flask application serving the build destination."""
        root = os.path.join(
            self.app.root_path,
            self.app.config['STATIC_BUILDER_DESTINATION']
        )
        
        def dispatch_request():
            try:
                path = request.path
                if path.endswith('/'):
                    path += 'index.html'
                assert path.startswith('/')
                return send_from_directory(root, path[1:])
            except HTTPException, e:
                # eg. NotFound
                return e
        
        app = Flask(__name__)
        # Do not use the URL map
        app.dispatch_request = dispatch_request
        return app

    def static_files_urls(self):
        """URL generator for static files for app and all registered modules.
        """
        send_static_file = unwrap_method(Flask.send_static_file)
        # Assumption about a Flask internal detail:
        # Flask and Module inherit the same method.
        # This will break loudly if the assumption isn't valid anymore in
        # a future version of Flask
        assert unwrap_method(Module.send_static_file) is send_static_file
        
        for rule in self.app.url_map.iter_rules():
            view = self.app.view_functions[rule.endpoint]
            if unwrap_method(view) is not send_static_file:
                continue
            # Found an URL rule for the static files view
            root = os.path.join(method_self(view).root_path, 'static')
            if not os.path.isdir(root):
                # No 'static' directory for this app/module.
                continue
            for filename in walk_directory(root):
                yield rule.endpoint, {'filename': filename}

    def no_argument_rules_urls(self):
        """URL generator for URL rules that take no arguments."""
        for rule in self.app.url_map.iter_rules():
            if not rule.arguments:
                yield rule.endpoint, {}


def walk_directory(root):
    """Recursively walk the `root` directory and yield slash-separated paths
    relative to the root.
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

