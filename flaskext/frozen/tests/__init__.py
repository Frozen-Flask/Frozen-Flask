# coding: utf8
from __future__ import with_statement

import unittest
import tempfile
import shutil
import os.path
from contextlib import contextmanager

from flaskext.frozen import Freezer, walk_directory
from . import test_app


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
        other_dir = os.path.dirname(this_dir)
        self.assert_(not diff(this_dir, this_dir))
        self.assert_(diff(this_dir, other_dir))


class TestWalkDirectory(unittest.TestCase):
    def test_walk_directory(self):
        self.assertEquals(
            set(f for f in walk_directory(os.path.dirname(test_app.__file__))
                if not f.endswith(('.pyc', '.pyo'))),
            set(['__init__.py', 'static/style.css', 'admin/__init__.py',
                 'admin/static/style.css'])
        )


class TestBuilder(unittest.TestCase):
    expected_output = {
        '/': 'Main index',
        '/admin/': 'Admin index',
        '/robots.txt': 'User-agent: *\nDisallow: /',
        '/product_0/': 'Product num 0',
        '/product_1/': 'Product num 1',
        '/product_2/': 'Product num 2',
        '/static/style.css': '/* Main CSS */\n',
        '/admin/static/style.css': '/* Admin CSS */\n',
        '/where_am_i/': '/where_am_i/ http://localhost/where_am_i/',
        u'/page/I løvë Unicode/'.encode('utf8'):
            u'Hello\xa0World! I løvë Unicode'.encode('utf8'),
    }
    filenames = {
        '/': 'index.html',
        '/admin/': 'admin/index.html',
        '/robots.txt': 'robots.txt',
        '/product_0/': 'product_0/index.html',
        '/product_1/': 'product_1/index.html',
        '/product_2/': 'product_2/index.html',
        '/static/style.css': 'static/style.css',
        '/admin/static/style.css': 'admin/static/style.css',
        '/where_am_i/': 'where_am_i/index.html',
        u'/page/I løvë Unicode/'.encode('utf8'):
            u'page/I løvë Unicode/index.html'.encode('utf8'),
    }
    app_extra_config = {}
    
    @contextmanager
    def built_app(self):
        with temp_directory() as temp:
            app, freezer = test_app.init_app()
            app.config['FREEZER_DESTINATION'] = temp
            app.config.update(self.app_extra_config)
            urls = freezer.freeze()
            yield temp, app, freezer, urls
    
    def test_all_urls_method(self):
        app, freezer = test_app.init_app()
        # Do not use set() here: also test that URLs are not duplicated.
        self.assertEquals(sorted(freezer.all_urls()),
                          sorted(self.expected_output))
        
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
        with self.built_app() as (temp, app, freezer, urls):
            temp = temp
            expected_files = set(self.filenames.itervalues())
            # No other files
            self.assertEquals(set(walk_directory(temp)), expected_files)
            # create an empty file
            os.mkdir(os.path.join(temp, 'extra'))
            open(os.path.join(temp, 'extra', 'extra.txt'), 'wb').close()
            # files in the destination that were not just built are removed
            freezer.freeze()
            self.assertEquals(set(walk_directory(temp)), expected_files)
            self.assert_(not os.path.exists(os.path.join(temp, 'extra')))

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
                self.assert_(not diff(temp, temp2))


class TestBaseURL(TestBuilder):
    app_extra_config = {'FREEZER_BASE_URL': 'http://example/myapp/'}
    expected_output = TestBuilder.expected_output.copy()
    expected_output['/where_am_i/'] = \
        '/myapp/where_am_i/ http://example/myapp/where_am_i/'


