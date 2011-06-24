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
import re

from werkzeug.exceptions import HTTPException
from flask import Flask, Module, url_for, request, send_from_directory

try:
    from collections import Mapping
    def is_mapping(obj):
        return isinstance(obj, Mapping)
except ImportError:
    # Python 2.5, no Abstract Base Classes. Default to duck-typing.
    def is_mapping(obj):
        return hasattr(obj, 'keys')


__all__ = ['Freezer']
class Freezer(object):
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
    def __init__(self, app=None, with_static_files=True,
                 with_no_argument_rules=True):
        self.url_generators = []
        self.excluded_patterns=[]
        if with_static_files:
            self.register_generator(self.static_files_urls)
        if with_no_argument_rules:
            self.register_generator(self.no_argument_rules_urls)
        self.init_app(app)
    
    def init_app(self, app):
        self.app = app
        if app:
            app.config.setdefault('FREEZER_DESTINATION', 'build')
            app.config.setdefault('FREEZER_BASE_URL', 'http://localhost/')
            app.config.setdefault('FREEZER_OVERWRITE', True)
    
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
    
    def exclude_pattern(self,pattern):
        """Prevent download of urls matching ``pattern``.

        :param pattern: A regular expression
        :type pattern: A string
        """
        self.excluded_patterns.append(re.compile(pattern))
    
    @property
    def root(self):
        """The build destination."""
        # unicode() will raise if the path is not ASCII or already unicode.
        return os.path.join(
            self.app.root_path,
            self.app.config['FREEZER_DESTINATION']
        )
    
    #note that these patterns are somewhat liberal
    #for example aaahref='link' would be matched
    #we assume false positives are ok, however, you can always exclude them
    """A pattern for matching links in html.

    This includes both links in an ``a`` or ``img`` tag.
    They are structured as follows:

    #. the string 'href' or 'src'
    #. optional whitespace
    #. an equal (=) sign
    #. optional whitespace
    #. an optional single (') or double quote (") character
    #. optional whitespace
    #. a string of characters (the link to be captured)
    #. optional whitespace
    #. closing '>', whitespace, single (') quote, or double quote (") character
       where the single/double quotes match up with the initial single/double
       quote

    """
    _html_url_ref_pattern=re.compile('(?:(?:href)|(?:src))\\s*=\\s*([\'"]?)\\s*([^"\\s>]+)\\s*\\1')

    """A pattern for matching a link in css.

    Defined as follows:

    #. the string 'url('
    #. optional whitespace
    #. an optional single (') or double quote (")
    #. optional whitespace
    #. a string of characters (the link to be captured)
    #. optional whitespace
    #. a closing single (') quote, or double quote (") matching the initial quote
    #. optional whitespace
    #. a closing paren ())

    """
    _css_url_ref_pattern=re.compile('url\\(\\s*(["\']?)\\s*([^\\s"]+)\\s*\\1\\s*\\)')

    """
    :param content: html/css text
    :Returns: a generator yeilding all links (as defined above) in content.
    """
    def _extract_links(self,content):
        #we search for both css and html links in content regardless of type
        #this is since html can contain embedded css and looking for html links
        #in css can't hurt
        for pattern in (self._html_url_ref_pattern,self._css_url_ref_pattern):
            for match in pattern.finditer(content):
                link=match.group(2)
                #fix for greedily grabbing single quotes inside a single quoted string
                if match.group(1)=="'" and "'" in link:
                    link=link[:link.find("'")]
                #fix for greedily grabbing close parent ()) inside an unquoted string
                if pattern == self._css_url_ref_pattern and not match.group(1) and ')' in link:
                    yield link[:link.find(')')]
                yield link
    
    def _is_url_excluded(self,url):
        """Test if ``url`` should be excluded by matching against all
           ``excluded_patterns``"""
        for pattern in self.excluded_patterns:
            if pattern.match(url):
                return True
        return False
    def _contains_links(self,file_name):
        """Test if a file with ``file_name`` should be scanned for links
           by seeing if it's extension is .css/.html/.xhtml"""
        for extension in ('html','css','xhtml'):
            if file_name.endswith('.'+extension):
                return True
        return False
        
    def freeze(self):
        """Clean the destination and build all URLs from generators."""
        overwrite_destination = self.app.config['FREEZER_OVERWRITE']
        if not os.path.isdir(self.root):
            os.makedirs(self.root)
        previous_files = set(
            os.path.join(self.root, *name.split('/'))
            for name in walk_directory(self.root)
        )
        seen_urls = set()
        built_files = set()
        urls=[u for u in self.all_urls()]
        while urls:
            url=urls.pop()
            if url in seen_urls:
                # Don't build the same URL more than once
                continue
            if self._is_url_excluded(url):
                continue
            seen_urls.add(url)
            new_filename,content = self._build_one(url)
            if self._contains_links(new_filename):
                for link in self._extract_links(content):
                    if not ':' in link: #url is not external
                        if '?' in link:#strip query
                            url=url[:url.rfind('?')]
                        if '#' in link:#strip anchor tag
                            url=url[:url.rfind('#')]
                        if not link.startswith('/'):#resolve relative paths
                            link=urlparse.urljoin(url,link)
                        if url:
                            urls.append(link)
            built_files.add(new_filename)
        if overwrite_destination:
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
        """
        base_url = self.app.config['FREEZER_BASE_URL']
        script_name = urlparse.urlsplit(base_url).path.rstrip('/')
        # A request context is required to use url_for
        with self.app.test_request_context(base_url=script_name):
            for generator in self.url_generators:
                for generated in generator():
                    if isinstance(generated, basestring):
                        url = generated
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
                    # Flask.url_for "quotes" URLs, eg. a space becomes %20
                    url = urllib.unquote(url)
                    if url.startswith(('http:', 'https:')):
                        raise ValueError('External URLs not supported: ' + url)
                        
                    yield url

    def _build_one(self, url):
        """Get the given ``url`` from the app and write the matching file.
        """
        client = self.app.test_client()
        base_url = self.app.config['FREEZER_BASE_URL']
        response = client.get(url, follow_redirects=True, base_url=base_url)
        # The client follows redirects by itself
        # Any other status code is probably an error
        if not(response.status_code == 200):
            raise ValueError('Unexpected status %r on URL %s' \
                % (response.status, url))

        destination_path = url + 'index.html' if url.endswith('/') else url

        # Most web servers guess the mime type of static files by their
        # filename.  Check that this guess is consistent with the actual
        # Content-Type header we got from the app.
        basename = destination_path.rsplit('/', 1)[-1]
        guessed_type, guessed_encoding = mimetypes.guess_type(basename)
        if not guessed_type:
            # Used by most server when they can not determine the type
            guessed_type = 'application/octet-stream'
        if not guessed_type == response.mimetype:
            raise ValueError(
                'Filename extension of %r (type %s) does not match Content-Type:'
                ' %s' % (basename, guessed_type, response.content_type))

        # Remove the initial slash that should always be there
        assert destination_path[0] == '/'
        destination_path = destination_path[1:]

        filename = os.path.join(self.root, *destination_path.split('/'))
        dirname = os.path.dirname(filename)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)
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
        return (filename,content)

    def serve(self, **options):
        """Run an HTTP server on the result of the build.

        :param options: passed to ``app.run()``.
        """
        self.make_static_app().run(**options)

    def make_static_app(self):
        """Return a Flask application serving the build destination."""
        root = os.path.join(
            self.app.root_path,
            self.app.config['FREEZER_DESTINATION']
        )

        def dispatch_request():
            try:
                # request.path is unicode, but the freezer previously wrote
                # to UTF-8 filenames, so encode to UTF-8 now.
                path = request.path.encode('utf8')
                if path.endswith('/'):
                    path += 'index.html'
                assert path.startswith('/')
                # Disable etags because of a Flask bug:
                # https://github.com/mitsuhiko/flask/pull/237
                # They are useless for tests anyway.
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
