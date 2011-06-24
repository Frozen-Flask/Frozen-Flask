# coding: utf8
from __future__ import with_statement

import unittest
import tempfile
import shutil
import os.path
import os
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
        '/': 'Main index href="/page/crawled/"',
        '/some/nested/page/':'url("../../../product_7/")',
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
    excluded_urls=["/page/excluded"]
    crawled_output={
        '/page/crawled/': u'Hello\xa0World! crawled'.encode('utf8'),
        '/product_7/': 'Product num 7'
    }
    all_output=dict(expected_output,**crawled_output)
    filenames = {
        '/': 'index.html',
        '/some/nested/page/':'some/nested/page/index.html',
        '/some/nested/page/':'some/nested/page/index.html',
        '/admin/': 'admin/index.html',
        '/robots.txt': 'robots.txt',
        '/product_0/': 'product_0/index.html',
        '/product_1/': 'product_1/index.html',
        '/product_2/': 'product_2/index.html',
        '/product_7/': 'product_7/index.html',
        '/static/style.css': 'static/style.css',
        '/admin/static/style.css': 'admin/static/style.css',
        '/where_am_i/': 'where_am_i/index.html',
        u'/page/I løvë Unicode/'.encode('utf8'):
            u'page/I løvë Unicode/index.html'.encode('utf8'),
        '/page/crawled/':'page/crawled/index.html'
    }
    defer_init_app = True
    
    def do_extra_config(self, app, freezer):
        pass # To be overriden
    
    @contextmanager
    def built_app(self):
        with temp_directory() as temp:
            app, freezer = test_app.init_app(self.defer_init_app)
            app.config['FREEZER_DESTINATION'] = temp
            self.do_extra_config(app, freezer)
            urls = freezer.freeze()
            yield temp, app, freezer, urls
            
    def test_extract_links(self):
        with open(os.path.dirname(__file__)+"/test_content_links",'r') as links:
            content=read_file(os.path.dirname(__file__)+"/test_content")
            for link in Freezer()._extract_links(content):
                self.assertEquals(link,links.readline().rstrip())
                           
    def test_without_app(self):
        freezer = Freezer()
        self.assertRaises(Exception, freezer.freeze)
        
    def test_all_urls_method(self):
        app, freezer = test_app.init_app()
        # Do not use set() here: also test that URLs are not duplicated.
        expected=sorted(self.expected_output)
        expected.append(*self.excluded_urls)
        self.assertEquals(sorted(freezer.all_urls()),
                          sorted(expected))
        
    def test_built_urls(self):
        with self.built_app() as (temp, app, freezer, urls):
            self.assertEquals(set(urls), set(self.all_output))
            # Make sure it was not accidently used as a destination
            default = os.path.join(os.path.dirname(__file__), 'build')
            self.assert_(not os.path.exists(default))
            
    def test_contents(self):
        with self.built_app() as (temp, app, freezer, urls):
            for url, filename in self.filenames.iteritems():
                filename = os.path.join(freezer.root, *filename.split('/'))
                content = read_file(filename)
                self.assertEquals(content, self.all_output[url])

    def test_nothing_else_matters(self):
        with self.built_app() as (temp, app, freezer, urls):
            dest = app.config['FREEZER_DESTINATION']
            expected_files = set(self.filenames.itervalues())
            # No other files
            self.assertEqualsExceptUnicode(set(walk_directory(dest)),expected_files)
            # create an empty file
            os.mkdir(os.path.join(dest, 'extra'))
            open(os.path.join(dest, 'extra', 'extra.txt'), 'wb').close()
            # files in the destination that were not just built are removed
            freezer.freeze()
            self.assertEqualsExceptUnicode(set(walk_directory(dest)),expected_files)
            self.assert_(not os.path.exists(os.path.join(dest, 'extra')))

    def test_something_else_matters(self):
        with self.built_app() as (temp, app, freezer, urls):
            app.config['FREEZER_OVERWRITE'] = False
            dest = app.config['FREEZER_DESTINATION']
            expected_files = set(self.filenames.itervalues())
            # No other files
            self.assertEqualsExceptUnicode(set(walk_directory(dest)),expected_files)
            # create an empty file
            os.mkdir(os.path.join(dest, 'extra'))
            open(os.path.join(dest, 'extra', 'extra.txt'), 'wb').close()
            expected_files.add('extra/extra.txt')
            # Verify that files in destination persist.
            freezer.freeze()
            self.assertEqualsExceptUnicode(set(walk_directory(dest)),expected_files)
            self.assert_(os.path.exists(os.path.join(dest, 'extra')))

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
    
    def assertEqualsExceptUnicode(self,set1,set2):
        diff=set1^set2
        if os.environ.get('FROZEN_FLASK_TEST_IGNORE_UNICODE','False')=='True':
            diff=set(filter(lambda s:'Unicode' not in s,diff))
        self.assertEquals(diff,set())


class TestInitApp(TestBuilder):
    defer_init_app = True


class TestBaseURL(TestBuilder):
    all_output = TestBuilder.all_output.copy()
    all_output['/where_am_i/'] = \
        '/myapp/where_am_i/ http://example/myapp/where_am_i/'

    def do_extra_config(self, app, freezer):
        app.config['FREEZER_BASE_URL'] = 'http://example/myapp/'


class TestNonexsistentDestination(TestBuilder):
    def do_extra_config(self, app, freezer):
        # frozen/htdocs does not exsist in the newly created temp directory,
        # the Freezer has to create it.
        app.config['FREEZER_DESTINATION'] = os.path.join(
            app.config['FREEZER_DESTINATION'], 'frozen', 'htdocs')


