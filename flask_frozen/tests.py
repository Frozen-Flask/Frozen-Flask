# coding: utf8
from __future__ import with_statement

import unittest
import tempfile
import shutil
import os.path
import warnings
from contextlib import contextmanager
from unicodedata import normalize

from flask_frozen import (Freezer, walk_directory,
    MissingURLGeneratorWarning, MimetypeMismatchWarning)
from . import test_app


try:
    # Since Python
    from warnings import catch_warnings
except ImportError:
    # Python 2.5
    class WarningMessage(object):
        def __init__(self, message, category, *args, **kwargs):
            self.message = message
            self.category = category

    @contextmanager
    def catch_warnings(record=False):
        assert record, 'record=False is not supported'

        _filters = warnings.filters
        warnings.filters = _filters[:]
        _showwarning = warnings.showwarning
        log = []
        def showwarning(*args, **kwargs):
            log.append(WarningMessage(*args, **kwargs))
        warnings.showwarning = showwarning

        try:
            yield log
        finally:
            warnings.filters = _filters
            warnings.showwarning = _showwarning


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
        return fd.read()


def diff(dir1, dir2):
    """Return the set of filenames that are not identical in dir1 and dir2"""
    files1 = set(walk_directory(dir1))
    files2 = set(walk_directory(dir2))
    # Files that are in 2 but not in 1
    different = set(files2 - files1)
    for filename in files1:
        name1 = os.path.join(dir1, *filename.split('/'))
        name2 = os.path.join(dir2, *filename.split('/'))
        if filename not in files2 or read_file(name1) != read_file(name2):
            different.add(filename)
    return different


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


class TestDiff(unittest.TestCase):
    def test_sanity(self):
        this_dir = os.path.dirname(__file__)
        other_dir = os.path.join(this_dir, 'test_app')
        self.assert_(not diff(this_dir, this_dir))
        self.assert_(diff(this_dir, other_dir))


class TestWalkDirectory(unittest.TestCase):
    def test_walk_directory(self):
        self.assertEquals(
            set(f for f in walk_directory(os.path.dirname(test_app.__file__))
                if not f.endswith(('.pyc', '.pyo'))),
            set(['__init__.py', 'static/style.css',
                 'admin/__init__.py', 'admin/admin_static/style.css'])
        )


class TestFreezer(unittest.TestCase):
    expected_output = {
        u'/': 'Main index /product_5/?revision=b12ef20',
        u'/admin/': 'Admin index',
        u'/robots.txt': 'User-agent: *\nDisallow: /',
        u'/product_0/': 'Product num 0',
        u'/product_1/': 'Product num 1',
        u'/product_2/': 'Product num 2',
        u'/product_3/': 'Product num 3',
        u'/product_4/': 'Product num 4',
        u'/product_5/': 'Product num 5',
        u'/static/style.css': '/* Main CSS */\n',
        u'/admin/css/style.css': '/* Admin CSS */\n',
        u'/where_am_i/': '/where_am_i/ http://localhost/where_am_i/',
        u'/page/I løvë Unicode/':
            u'Hello\xa0World! I løvë Unicode'.encode('utf8'),
    }
    filenames = {
        u'/': u'index.html',
        u'/admin/': u'admin/index.html',
        u'/robots.txt': u'robots.txt',
        u'/product_0/': u'product_0/index.html',
        u'/product_1/': u'product_1/index.html',
        u'/product_2/': u'product_2/index.html',
        u'/product_3/': u'product_3/index.html',
        u'/product_4/': u'product_4/index.html',
        u'/product_5/': u'product_5/index.html',
        u'/static/style.css': u'static/style.css',
        u'/admin/css/style.css': u'admin/css/style.css',
        u'/where_am_i/': u'where_am_i/index.html',
        u'/page/I løvë Unicode/': u'page/I løvë Unicode/index.html',
    }
    generated_by_url_for = [u'/product_3/', u'/product_4/', u'/product_5/']
    defer_init_app = True
    freezer_kwargs = None

    def do_extra_config(self, app, freezer):
        pass # To be overriden

    @contextmanager
    def make_app(self):
        with temp_directory() as temp:
            app, freezer = test_app.create_app(self.defer_init_app,
                                               self.freezer_kwargs)
            app.config['FREEZER_DESTINATION'] = temp
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
        self.assertEquals(set1, set2)

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
        self.assertEquals(sorted(freezer.all_urls()), expected)

    def test_built_urls(self):
        with self.built_app() as (temp, app, freezer, urls):
            self.assertEquals(set(urls), set(self.expected_output))
            # Make sure it was not accidently used as a destination
            default = os.path.join(os.path.dirname(__file__), 'build')
            self.assert_(not os.path.exists(default))

    def test_contents(self):
        with self.built_app() as (temp, app, freezer, urls):
            for url, filename in self.filenames.iteritems():
                filename = os.path.join(freezer.root, *filename.split('/'))
                content = read_file(filename)
                self.assertEquals(content, self.expected_output[url])

    def test_nothing_else_matters(self):
        self._extra_files(remove=True)

    def test_something_else_matters(self):
        self._extra_files(remove=False)

    def _extra_files(self, remove):
        with self.built_app() as (temp, app, freezer, urls):
            app.config['FREEZER_REMOVE_EXTRA_FILES'] = remove
            dest = unicode(app.config['FREEZER_DESTINATION'])
            expected_files = set(self.filenames.itervalues())

            # No other files
            self.assertFilenamesEqual(walk_directory(dest), expected_files)

            # create an empty file
            os.mkdir(os.path.join(dest, 'extra'))
            open(os.path.join(dest, 'extra', 'extra.txt'), 'wb').close()
            if not remove:
                expected_files.add(u'extra/extra.txt')

            # Verify that files in destination persist.
            freezer.freeze()
            self.assertFilenamesEqual(walk_directory(dest), expected_files)

            exists = os.path.exists(os.path.join(dest, 'extra'))
            if remove:
                self.assert_(not exists)
            else:
                self.assert_(exists)

    def test_transitivity(self):
        with self.built_app() as (temp, app, freezer, urls):
            with temp_directory() as temp2:
                # Run the freezer on it's own output
                app2 = freezer.make_static_app()
                app2.config['FREEZER_DESTINATION'] = temp2
                app2.debug = True
                freezer2 = Freezer(app2)
                freezer2.register_generator(self.filenames.iterkeys)
                freezer2.freeze()
                destination = app.config['FREEZER_DESTINATION']
                self.assertEquals(diff(destination, temp2), set())

    def test_error_on_external_url(self):
        for url in ['http://example.com/foo', '//example.com/foo',
                    'file:///foo']:
            with self.make_app() as (temp, app, freezer):
                @freezer.register_generator
                def external_url():
                    yield url

                try:
                    freezer.freeze()
                except ValueError, e:
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
                self.assertEquals(len(logged_warnings), 1)
                self.assertEquals(logged_warnings[0].category,
                                  MissingURLGeneratorWarning)

    def test_wrong_default_mimetype(self):
        with self.make_app() as (temp, app, freezer):
            @app.route(u'/no-file-extension')
            def no_extension():
                return '42', 200, {'Content-Type': 'image/png'}

            with catch_warnings(record=True) as logged_warnings:
                warnings.simplefilter("always")
                freezer.freeze()
                self.assertEquals(len(logged_warnings), 1)
                self.assertEquals(logged_warnings[0].category,
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
                self.assertEquals(len(logged_warnings), 1)
                self.assertEquals(logged_warnings[0].category,
                                  MimetypeMismatchWarning)


class TestInitApp(TestFreezer):
    defer_init_app = True


class TestBaseURL(TestFreezer):
    expected_output = TestFreezer.expected_output.copy()
    expected_output['/'] = 'Main index /myapp/product_5/?revision=b12ef20'
    expected_output['/where_am_i/'] = \
        '/myapp/where_am_i/ http://example/myapp/where_am_i/'

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

# with_no_argument_rules=False and with_static_files=False are
# not tested as they produces (expected!) warnings
