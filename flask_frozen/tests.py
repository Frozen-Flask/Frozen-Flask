# coding: utf8
"""
    flask_frozen.tests
    ~~~~~~~~~~~~~~~~~~

    Automated test suite for Frozen-Flask
    Run with :
        $ python -m flask_frozen.tests

    :copyright: (c) 2010-2012 by Simon Sapin.
    :license: BSD, see LICENSE for more details.

"""

import datetime
import time
import unittest
import tempfile
import shutil
import os.path
import warnings
import hashlib
from contextlib import contextmanager
from unicodedata import normalize
from warnings import catch_warnings
import sys
import subprocess

from flask_frozen import (Freezer, walk_directory,
    FrozenFlaskWarning, MissingURLGeneratorWarning, MimetypeMismatchWarning,
    NotFoundWarning, RedirectWarning)
from flask_frozen import test_app
import flask_frozen

try:
    unicode
except NameError:  # Python 3
    unicode = str


@contextmanager
def temp_directory():
    """This context manager gives the path to a new temporary directory that
    is deleted (with all it's content) at the end of the with block.
    """
    directory = tempfile.mkdtemp()
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def read_file(filename):
    with open(filename, 'rb') as fd:
        content = fd.read()
        if len(content) < 200:
            return content
        else:
            return hashlib.md5(content).hexdigest()


def read_all(directory):
    return set(
        (filename, read_file(os.path.join(directory, *filename.split('/'))))
        for filename in walk_directory(directory))


class TestTempDirectory(unittest.TestCase):
    def test_removed(self):
        with temp_directory() as temp:
            assert os.path.isdir(temp)
        # should be removed now
        assert not os.path.exists(temp)

    def test_exception(self):
        try:
            with temp_directory() as temp:
                assert os.path.isdir(temp)
                1 / 0
        except ZeroDivisionError:
            pass
        else:
            assert False, 'Exception did not propagate'
        assert not os.path.exists(temp)

    def test_writing(self):
        with temp_directory() as temp:
            filename = os.path.join(temp, 'foo')
            with open(filename, 'w') as fd:
                fd.write('foo')
            assert os.path.isfile(filename)
        assert not os.path.exists(temp)
        assert not os.path.exists(filename)


class TestWalkDirectory(unittest.TestCase):
    def test_walk_directory(self):
        self.assertEqual(
            set(f for f in walk_directory(os.path.dirname(test_app.__file__))
                if not f.endswith(('.pyc', '.pyo'))),
            set(['__init__.py', 'static/style.css', 'static/favicon.ico',
                 'static/main.js', 'admin/__init__.py',
                 'admin/admin_static/style.css', 'admin/templates/admin.html'])
        )


class TestFreezer(unittest.TestCase):
    # URL -> expected bytes content of the generated file
    expected_output = {
        u'/': b'Main index /product_5/?revision=b12ef20',
        u'/redirect/': b'Main index /product_5/?revision=b12ef20',
        u'/admin/': b'Admin index\n'
            b'<a href="/page/I%20l%C3%B8v%C3%AB%20Unicode/">Unicode test</a>\n'
            b'<a href="/page/octothorp/?query_foo=bar#introduction">'
            b'URL parsing test</a>',
        u'/robots.txt': b'User-agent: *\nDisallow: /',
        u'/favicon.ico': read_file(test_app.FAVICON),
        u'/product_0/': b'Product num 0',
        u'/product_1/': b'Product num 1',
        u'/product_2/': b'Product num 2',
        u'/product_3/': b'Product num 3',
        u'/product_4/': b'Product num 4',
        u'/product_5/': b'Product num 5',
        u'/static/favicon.ico': read_file(test_app.FAVICON),
        u'/static/style.css': b'/* Main CSS */\n',
        u'/static/main.js': b'/* Main JS */\n',
        u'/admin/css/style.css': b'/* Admin CSS */\n',
        u'/where_am_i/': b'/where_am_i/ http://localhost/where_am_i/',
        u'/page/foo/': u'Hello\xa0World! foo'.encode('utf8'),
        u'/page/I løvë Unicode/':
            u'Hello\xa0World! I løvë Unicode'.encode('utf8'),
        u'/page/octothorp/':
            u'Hello\xa0World! octothorp'.encode('utf8'),
    }

    # URL -> path to the generated file, relative to the build destination root
    filenames = {
        u'/': u'index.html',
        u'/redirect/': u'redirect/index.html',
        u'/admin/': u'admin/index.html',
        u'/robots.txt': u'robots.txt',
        u'/favicon.ico': u'favicon.ico',
        u'/product_0/': u'product_0/index.html',
        u'/product_1/': u'product_1/index.html',
        u'/product_2/': u'product_2/index.html',
        u'/product_3/': u'product_3/index.html',
        u'/product_4/': u'product_4/index.html',
        u'/product_5/': u'product_5/index.html',
        u'/static/style.css': u'static/style.css',
        u'/static/main.js': u'static/main.js',
        u'/static/favicon.ico': u'static/favicon.ico',
        u'/admin/css/style.css': u'admin/css/style.css',
        u'/where_am_i/': u'where_am_i/index.html',
        u'/page/foo/': u'page/foo/index.html',
        u'/page/I løvë Unicode/': u'page/I løvë Unicode/index.html',
        u'/page/octothorp/': u'page/octothorp/index.html',
    }

    assert set(expected_output.keys()) == set(filenames.keys())
    generated_by_url_for = [u'/product_3/', u'/product_4/', u'/product_5/',
                            u'/page/I løvë Unicode/',
                            u'/page/octothorp/']
    defer_init_app = True
    freezer_kwargs = None

    maxDiff = None

    def do_extra_config(self, app, freezer):
        pass  # To be overridden

    @contextmanager
    def make_app(self):
        with temp_directory() as temp:
            app, freezer = test_app.create_app(self.defer_init_app,
                                               self.freezer_kwargs)
            app.config['FREEZER_DESTINATION'] = temp
            app.debug = True
            self.do_extra_config(app, freezer)
            yield temp, app, freezer

    @contextmanager
    def make_app_with_404(self):
        # Build an app with a link to a non-existent route
        with self.make_app() as (temp, app, freezer):
            @freezer.register_generator
            def non_existent_url():
                yield '/404/'
            yield temp, app, freezer

    @contextmanager
    def built_app(self):
        with self.make_app() as (temp, app, freezer):
            urls = freezer.freeze()
            yield temp, app, freezer, urls

    def assertFilenamesEqual(self, set1, set2):
        # Fix for https://github.com/SimonSapin/Frozen-Flask/issues/5
        set1 = sorted(normalize('NFC', name) for name in set1)
        set2 = sorted(normalize('NFC', name) for name in set2)
        self.assertEqual(set1, set2)

    def test_without_app(self):
        freezer = Freezer()
        self.assertRaises(Exception, freezer.freeze)

    def test_all_urls_method(self):
        with self.built_app() as (temp, app, freezer, urls):
            expected = sorted(self.expected_output)
            # url_for() calls are not logged when just calling .all_urls()
            for url in self.generated_by_url_for:
                if url in expected:
                    expected.remove(url)
            # Do not use set() here: also test that URLs are not duplicated.
            self.assertEqual(sorted(freezer.all_urls()), expected)

    def test_built_urls(self):
        with self.built_app() as (temp, app, freezer, urls):
            self.assertEqual(set(urls), set(self.expected_output))
            # Make sure it was not accidentally used as a destination
            default = os.path.join(os.path.dirname(__file__), 'build')
            self.assertTrue(not os.path.exists(default))

    def test_contents(self):
        with self.built_app() as (temp, app, freezer, urls):
            for url, filename in self.filenames.items():
                filename = os.path.join(freezer.root, *filename.split('/'))
                content = read_file(filename)
                self.assertEqual(content, self.expected_output[url])

    def test_nothing_else_matters(self):
        self._extra_files(removed=True)

    def test_something_else_matters(self):
        self._extra_files(remove_extra=False, removed=False)

    def test_ignore_pattern(self):
        self._extra_files(ignore=['extraa'], removed=True)   # Not a match
        self._extra_files(ignore=['extr*'], removed=False)   # Match

    def _extra_files(self, removed, remove_extra=True, ignore=()):
        with self.built_app() as (temp, app, freezer, urls):
            app.config['FREEZER_REMOVE_EXTRA_FILES'] = remove_extra
            app.config['FREEZER_DESTINATION_IGNORE'] = ignore
            dest = unicode(app.config['FREEZER_DESTINATION'])
            expected_files = set(self.filenames.values())

            # No other files
            self.assertFilenamesEqual(walk_directory(dest), expected_files)

            # create an empty file
            os.mkdir(os.path.join(dest, 'extra'))
            open(os.path.join(dest, 'extra', 'extra.txt'), 'wb').close()

            # Verify that files in destination persist.
            freezer.freeze()

            exists = os.path.exists(os.path.join(dest, 'extra'))
            if removed:
                self.assertTrue(not exists)
            else:
                self.assertTrue(exists)
                expected_files.add(u'extra/extra.txt')
            self.assertFilenamesEqual(walk_directory(dest), expected_files)

    def test_transitivity(self):
        with self.built_app() as (temp, app, freezer, urls):
            with temp_directory() as temp2:
                # Run the freezer on it's own output
                app2 = freezer.make_static_app()
                app2.config['FREEZER_DESTINATION'] = temp2
                app2.debug = True
                freezer2 = Freezer(app2)
                freezer2.register_generator(self.filenames.keys)
                freezer2.freeze()
                destination = app.config['FREEZER_DESTINATION']
                self.assertEqual(read_all(destination), read_all(temp2))

    def test_error_on_external_url(self):
        for url in ['http://example.com/foo', '//example.com/foo',
                    'file:///foo']:
            with self.make_app() as (temp, app, freezer):
                @freezer.register_generator
                def external_url():
                    yield url

                try:
                    freezer.freeze()
                except ValueError as e:
                    assert 'External URLs not supported' in e.args[0]
                else:
                    assert False, 'Expected ValueError'

    def test_error_on_internal_404(self):
        with self.make_app_with_404() as (temp, app, freezer):
            # Test standard behaviour with 404 errors (freeze failure)
            try:
                freezer.freeze()
            except ValueError as e:
                error_msg = "Unexpected status '404 NOT FOUND' on URL /404/"
                assert error_msg in e.args[0]
            else:
                assert False, 'Expected ValueError'

    def test_warn_on_internal_404(self):
        with self.make_app_with_404() as (temp, app, freezer):
            # Enable 404 errors ignoring
            app.config['FREEZER_IGNORE_404_NOT_FOUND'] = True
            # Test warning with 404 errors when we choose to ignore them
            with catch_warnings(record=True) as logged_warnings:
                warnings.simplefilter("always")
                freezer.freeze()
                self.assertEqual(len(logged_warnings), 1)
                self.assertEqual(logged_warnings[0].category,
                                 NotFoundWarning)

    def test_error_on_redirect(self):
        with self.make_app() as (temp, app, freezer):
            # Enable errors on redirects.
            app.config['FREEZER_REDIRECT_POLICY'] = 'error'
            try:
                freezer.freeze()
            except ValueError as e:
                error_msg = "Unexpected status '302 FOUND' on URL /redirect/"
                assert error_msg in e.args[0]
            else:
                assert False, 'Expected ValueError'

    def test_warn_on_redirect(self):
        with self.make_app() as (temp, app, freezer):
            # Enable ignoring redirects.
            app.config['FREEZER_REDIRECT_POLICY'] = 'ignore'
            # Test warning with 302 errors when we choose to ignore them
            with catch_warnings(record=True) as logged_warnings:
                warnings.simplefilter("always")
                freezer.freeze()
                self.assertEqual(len(logged_warnings), 1)
                self.assertEqual(logged_warnings[0].category,
                                 RedirectWarning)

    def test_warn_on_missing_generator(self):
        with self.make_app() as (temp, app, freezer):
            # Add a new endpoint without URL generator
            @app.route('/extra/<some_argument>')
            def external_url(some_argument):
                return some_argument

            with catch_warnings(record=True) as logged_warnings:
                warnings.simplefilter("always")
                freezer.freeze()
                self.assertEqual(len(logged_warnings), 1)
                self.assertEqual(logged_warnings[0].category,
                                 MissingURLGeneratorWarning)

    def test_wrong_default_mimetype(self):
        with self.make_app() as (temp, app, freezer):
            @app.route(u'/no-file-extension')
            def no_extension():
                return '42', 200, {'Content-Type': 'image/png'}

            with catch_warnings(record=True) as logged_warnings:
                warnings.simplefilter("always")
                freezer.freeze()
                self.assertEqual(len(logged_warnings), 1)
                self.assertEqual(logged_warnings[0].category,
                                 MimetypeMismatchWarning)

    def test_default_mimetype(self):
        with self.make_app() as (temp, app, freezer):
            @app.route(u'/no-file-extension')
            def no_extension():
                return '42', 200, {'Content-Type': 'application/octet-stream'}
            freezer.freeze()

    def test_unknown_extension(self):
        with self.make_app() as (temp, app, freezer):
            @app.route(u'/unknown-extension.fuu')
            def no_extension():
                return '42', 200, {'Content-Type': 'application/octet-stream'}
            freezer.freeze()

    def test_configured_default_mimetype(self):
        with self.make_app() as (temp, app, freezer):
            app.config['FREEZER_DEFAULT_MIMETYPE'] = 'image/png'
            @app.route(u'/no-file-extension')
            def no_extension():
                return '42', 200, {'Content-Type': 'image/png'}
            freezer.freeze()

    def test_wrong_configured_mimetype(self):
        with self.make_app() as (temp, app, freezer):
            app.config['FREEZER_DEFAULT_MIMETYPE'] = 'image/png'
            @app.route(u'/no-file-extension')
            def no_extension():
                return '42', 200, {'Content-Type': 'application/octet-stream'}
            with catch_warnings(record=True) as logged_warnings:
                warnings.simplefilter("always")
                freezer.freeze()
                self.assertEqual(len(logged_warnings), 1)
                self.assertEqual(logged_warnings[0].category,
                                 MimetypeMismatchWarning)

    def test_skip_existing_files(self):
        with self.make_app() as (temp, app, freezer):
            app.config['FREEZER_SKIP_EXISTING'] = True
            with open(os.path.join(temp, 'skipped.html'), 'w') as f:
                f.write("6*9")
            @app.route(u'/skipped.html')
            def skipped():
                return '42'
            freezer.freeze()
            with open(os.path.join(temp, 'skipped.html')) as f:
                self.assertEqual(f.read(), '6*9')

class TestWarnings(unittest.TestCase):
    def test_warnings_share_common_superclass(self):
        with catch_warnings(record=True) as logged_warnings:
            # ignore all warnings:
            warnings.simplefilter('ignore')
            # but don't ignore FrozenFlaskWarning
            warnings.filterwarnings('always', category=FrozenFlaskWarning)
            # warn each of our warnings:
            warnings_frozen_flask = (MissingURLGeneratorWarning,
                                     MimetypeMismatchWarning,
                                     NotFoundWarning,
                                     RedirectWarning)
            for warning in warnings_frozen_flask:
                warnings.warn('test', warning)
            # warn something different:
            warnings.warn('test', PendingDeprecationWarning)
            self.assertEqual(len(logged_warnings), len(warnings_frozen_flask))


class TestInitApp(TestFreezer):
    defer_init_app = True


class TestBaseURL(TestFreezer):
    expected_output = TestFreezer.expected_output.copy()
    expected_output['/'] = b'Main index /myapp/product_5/?revision=b12ef20'
    expected_output['/where_am_i/'] = \
        b'/myapp/where_am_i/ http://example/myapp/where_am_i/'
    expected_output['/admin/'] = (
        b'Admin index\n'
        b'<a href="/myapp/page/I%20l%C3%B8v%C3%AB%20Unicode/">Unicode test</a>\n'
        b'<a href="/myapp/page/octothorp/?query_foo=bar#introduction">'
        b'URL parsing test</a>')

    def do_extra_config(self, app, freezer):
        app.config['FREEZER_BASE_URL'] = 'http://example/myapp/'


class TestNonexsistentDestination(TestFreezer):
    def do_extra_config(self, app, freezer):
        # frozen/htdocs does not exist in the newly created temp directory,
        # the Freezer has to create it.
        app.config['FREEZER_DESTINATION'] = os.path.join(
            app.config['FREEZER_DESTINATION'], 'frozen', 'htdocs')


class TestServerName(TestFreezer):
    def do_extra_config(self, app, freezer):
        app.config['SERVER_NAME'] = 'example.net'
    expected_output = TestFreezer.expected_output.copy()
    expected_output[u'/where_am_i/'] = (
        b'/where_am_i/ http://example.net/where_am_i/')


class TestWithoutUrlForLog(TestFreezer):
    freezer_kwargs = dict(log_url_for=False)

    expected_output = TestFreezer.expected_output.copy()
    filenames = TestFreezer.filenames.copy()
    for url in TestFreezer.generated_by_url_for:
        del expected_output[url]
        del filenames[url]


class TestRelativeUrlFor(TestFreezer):
    def do_extra_config(self, app, freezer):
        app.config['FREEZER_RELATIVE_URLS'] = True

    expected_output = TestFreezer.expected_output.copy()
    expected_output['/admin/'] = (
        b'Admin index\n'
        b'<a href="../page/I%20l%C3%B8v%C3%AB%20Unicode/index.html">'
        b'Unicode test</a>\n'
        b'<a href="../page/octothorp/index.html?query_foo=bar#introduction">'
        b'URL parsing test</a>')


class TestStaticIgnore(TestFreezer):
    def do_extra_config(self, app, freezer):
        app.config['FREEZER_STATIC_IGNORE'] = ['*.js',]

    expected_output = TestFreezer.expected_output.copy()
    filenames = TestFreezer.filenames.copy()
    del expected_output[u'/static/main.js']
    del filenames[u'/static/main.js']

class TestLastModifiedGenerator(TestFreezer):
    def test_generate_last_modified(self):
        """
            Yield two pages. One is last_modified in the past, and one is last_modified now.
            The first page should only be written on the first run.
            The second page should be written on both runs.
        """
        with self.make_app() as (temp, app, freezer):
            @app.route(u'/time/<when>/')
            def show_time(when):
                return when+datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            @freezer.register_generator
            def view_post():
                yield 'show_time', {'when': 'epoch'}, datetime.datetime.fromtimestamp(100000)
                yield 'show_time', {'when': 'now'}, datetime.datetime.now()

            freezer.freeze()

            first_mtimes = dict((k,os.path.getmtime(os.path.join(temp,'time',k,'index.html'))) for k in ['epoch', 'now'])

            time.sleep(2)

            freezer.freeze()

            second_mtimes = dict((k,os.path.getmtime(os.path.join(temp,'time',k,'index.html'))) for k in ['epoch', 'now'])

            self.assertEqual(first_mtimes['epoch'],second_mtimes['epoch'])
            self.assertNotEqual(first_mtimes['now'],second_mtimes['now'])

class TestPythonCompatibilityWarnings(unittest.TestCase):
    def test_importing_collections(self):
        flask_script_path = flask_frozen.__file__
        ps = subprocess.check_output([sys.executable, flask_script_path],
                                     stderr=subprocess.STDOUT)
        stderr = ps.decode('utf-8').lower()
        assert 'deprecationwarning' not in stderr
        assert 'using or importing the abcs' not in stderr

# with_no_argument_rules=False and with_static_files=False are
# not tested as they produces (expected!) warnings

if __name__ == '__main__':
    unittest.main()
