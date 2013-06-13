# coding: utf8
"""
    flask_frozen.tests
    ~~~~~~~~~~~~~~~~~~

    Automated test suite for Frozen-Flask

    :copyright: (c) 2010-2012 by Simon Sapin.
    :license: BSD, see LICENSE for more details.

"""

import unittest
import tempfile
import shutil
import os.path
import warnings
import hashlib
from contextlib import contextmanager
from unicodedata import normalize
from warnings import catch_warnings

from flask_frozen import (Freezer, walk_directory,
    MissingURLGeneratorWarning, MimetypeMismatchWarning)
from flask_frozen import test_app

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
                 'admin/__init__.py', 'admin/admin_static/style.css',
                 'admin/templates/admin.html'])
        )


class TestFreezer(unittest.TestCase):
    # URL -> expected bytes content of the generated file
    expected_output = {
        u'/': b'Main index /product_5/?revision=b12ef20',
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
        pass # To be overriden

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
        app, freezer = test_app.create_app(freezer_kwargs=self.freezer_kwargs)
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
            # Make sure it was not accidently used as a destination
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
            @app.route(u'/unkown-extension.fuu')
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
        # frozen/htdocs does not exsist in the newly created temp directory,
        # the Freezer has to create it.
        app.config['FREEZER_DESTINATION'] = os.path.join(
            app.config['FREEZER_DESTINATION'], 'frozen', 'htdocs')


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


# with_no_argument_rules=False and with_static_files=False are
# not tested as they produces (expected!) warnings

if __name__ == '__main__':
    unittest.main()
