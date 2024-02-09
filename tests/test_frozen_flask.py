"""
    Automated test suite for Frozen-Flask.
    Run with pytest.

    :copyright: (c) 2010-2012 by Simon Sapin.
    :license: BSD, see LICENSE for more details.
"""

import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from subprocess import STDOUT, check_output
from unicodedata import normalize

import flask_frozen
from flask import redirect
from flask_frozen import (Freezer, FrozenFlaskWarning, MimetypeMismatchWarning,
                          MissingURLGeneratorWarning, NotFoundWarning,
                          RedirectWarning, walk_directory)
from pytest import raises, warns

import test_app


def read_all(directory):
    return {
        filename: (Path(directory) / filename).read_bytes()
        for filename in walk_directory(directory)}


def normalize_set(set):
    # Fix for https://github.com/SimonSapin/Frozen-Flask/issues/5
    return {normalize('NFC', name) for name in set}


def test_walk_directory():
    directory = Path(test_app.__file__).parent

    paths = {
        '__init__.py', 'static/favicon.ico', 'static/main.js',
        'admin/__init__.py', 'admin/templates/admin.html'}
    ignore_patterns = (
        ('*.pyc', '*.pyo', '*.css'),
        ('*.py?', '*/*/*.css', '*/*.css'),
        ('*.py?', '*.css', '/templates'),
        ('*.py?', '*.css', '/templates/*'),
        ('*.py?', '*.css', 'templates/*'),
        ('*.py?', '*.css', 'templates/admin.html'),
        ('*.py?', '*.css', 'tem*es/*'),
        ('*.py?', '*.css', '__init__.py/'),
        ('*.py?', '*.css', '/__init__.py/'),
    )
    for ignore in ignore_patterns:
        assert set(walk_directory(directory, ignore)) == paths
    assert {
        filename for filename in walk_directory(directory)
        if not filename.endswith(('.pyc', '.pyo', '.css'))} == paths

    paths = {path for path in paths if not path.startswith('admin/')}
    ignore_patterns = (
        ('*.py?', '*.css', '/admin'),
        ('*.py?', '*.css', 'admin/'),
        ('*.py?', '*.css', '/admin/'),
        ('*.py?', '*.css', '/a*n/'),
        ('*.py?', '*.css', 'admin/*'),
        ('*.py?', '*.css', 'admin*'),
        ('*.py?', '*.css', 'admin'),
        ('*.py?', '*.css', 'admin/__init__.py', 'templates'),
        ('*.py?', '*.css', 'admin/__init__.py', 'templates/'),
    )
    for ignore in ignore_patterns:
        assert set(walk_directory(directory, ignore)) == paths


def test_warnings_share_common_superclass():
    with warns() as logged_warnings:
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
        assert len(logged_warnings) == len(warnings_frozen_flask)


def test_importing_collections():
    flask_script_path = flask_frozen.__file__
    ps = check_output([sys.executable, flask_script_path], stderr=STDOUT)
    stderr = ps.decode().lower()
    assert 'deprecationwarning' not in stderr
    assert 'using or importing the abcs' not in stderr


class TestFreezer:
    # URL -> expected bytes content of the generated file
    expected_output = {
        '/': b'Main index /product_5/?revision=b12ef20',
        '/redirect/': b'Main index /product_5/?revision=b12ef20',
        '/admin/': (
            b'Admin index\n'
            b'<a href="/page/I%20l%C3%B8v%C3%AB%20Unicode/">Unicode test</a>\n'
            b'<a href="/page/octothorp/?query_foo=bar#introduction">'
            b'URL parsing test</a>'),
        '/robots.txt': b'User-agent: *\nDisallow: /',
        '/favicon.ico': Path(test_app.FAVICON).read_bytes(),
        '/product_0/': b'Product num 0',
        '/product_1/': b'Product num 1',
        '/product_2/': b'Product num 2',
        '/product_3/': b'Product num 3',
        '/product_4/': b'Product num 4',
        '/product_5/': b'Product num 5',
        '/static/favicon.ico': Path(test_app.FAVICON).read_bytes(),
        '/static/style.css': b'/* Main CSS */',
        '/static/main.js': b'/* Main JS */',
        '/admin/css/style.css': b'/* Admin CSS */',
        '/where_am_i/': b'/where_am_i/ http://localhost/where_am_i/',
        '/page/foo/': 'Hello\xa0World! foo'.encode(),
        '/page/I løvë Unicode/':
            'Hello\xa0World! I løvë Unicode'.encode(),
        '/page/octothorp/':
            'Hello\xa0World! octothorp'.encode(),
    }

    # URL -> path to the generated file, relative to the build destination root
    filenames = {
        '/': 'index.html',
        '/redirect/': 'redirect/index.html',
        '/admin/': 'admin/index.html',
        '/robots.txt': 'robots.txt',
        '/favicon.ico': 'favicon.ico',
        '/product_0/': 'product_0/index.html',
        '/product_1/': 'product_1/index.html',
        '/product_2/': 'product_2/index.html',
        '/product_3/': 'product_3/index.html',
        '/product_4/': 'product_4/index.html',
        '/product_5/': 'product_5/index.html',
        '/static/style.css': 'static/style.css',
        '/static/main.js': 'static/main.js',
        '/static/favicon.ico': 'static/favicon.ico',
        '/admin/css/style.css': 'admin/css/style.css',
        '/where_am_i/': 'where_am_i/index.html',
        '/page/foo/': 'page/foo/index.html',
        '/page/I løvë Unicode/': 'page/I løvë Unicode/index.html',
        '/page/octothorp/': 'page/octothorp/index.html',
    }

    assert set(expected_output.keys()) == set(filenames.keys())
    generated_by_url_for = ['/product_3/', '/product_4/', '/product_5/',
                            '/page/I løvë Unicode/',
                            '/page/octothorp/']
    defer_init_app = True
    freezer_kwargs = None
    with_404 = False

    def make_app(self, tmp_path, with_404=False):
        app, freezer = test_app.create_app(
            self.defer_init_app, self.freezer_kwargs)
        app.config['FREEZER_DESTINATION'] = tmp_path
        app.debug = True
        self.do_extra_config(app, freezer)
        if with_404:
            @freezer.register_generator
            def non_existent_url():
                yield '/404/'
        return app, freezer

    def freeze_app(self, tmp_path):
        app, freezer = self.make_app(tmp_path)
        return app, freezer, freezer.freeze()

    def do_extra_config(self, app, freezer):
        pass  # To be overridden

    def test_without_app(self):
        freezer = Freezer()
        with raises(Exception):
            freezer.freeze()

    def test_all_urls_method(self, tmp_path):
        app, freezer, urls = self.freeze_app(tmp_path)
        expected = sorted(self.expected_output)
        # url_for() calls are not logged when just calling .all_urls()
        for url in self.generated_by_url_for:
            if url in expected:
                expected.remove(url)
        # Do not use set() here: also test that URLs are not duplicated.
        assert sorted(freezer.all_urls()) == expected

    def test_built_urls(self, tmp_path):
        app, freezer, urls = self.freeze_app(tmp_path)
        assert set(urls) == set(self.expected_output)
        # Make sure it was not accidentally used as a destination
        default = Path(__file__).parent / 'build'
        assert not default.exists()

    def test_contents(self, tmp_path):
        app, freezer, urls = self.freeze_app(tmp_path)
        for url, filename in self.filenames.items():
            content = (freezer.root / filename).read_bytes()
            assert content == self.expected_output[url]

    def test_nothing_else_matters(self, tmp_path):
        self._extra_files(tmp_path, removed=True)

    def test_something_else_matters(self, tmp_path):
        self._extra_files(tmp_path, remove_extra=False, removed=False)

    def test_ignore_pattern(self, tmp_path):
        self._extra_files(tmp_path, ignore=['extro'], removed=True)  # No match
        self._extra_files(tmp_path, ignore=['extr*'], removed=False)  # Match

    def _extra_files(self, tmp_path, removed, remove_extra=True, ignore=()):
        app, freezer, urls = self.freeze_app(tmp_path)
        app.config['FREEZER_REMOVE_EXTRA_FILES'] = remove_extra
        app.config['FREEZER_DESTINATION_IGNORE'] = ignore
        dest = Path(app.config['FREEZER_DESTINATION'])
        expected_files = normalize_set(set(self.filenames.values()))

        # No other files
        assert normalize_set(walk_directory(dest)) == expected_files

        # Create an empty file
        (dest / 'extra').mkdir()
        (dest / 'extra' / 'extra.txt').touch()

        # Verify that files in destination persist
        freezer.freeze()

        if removed:
            assert not (dest / 'extra').exists()
        else:
            assert (dest / 'extra').exists()
            expected_files.add('extra/extra.txt')

        assert normalize_set(walk_directory(dest)) == expected_files

    def test_transitivity(self, tmp_path_factory):
        tmp_path_1 = tmp_path_factory.mktemp('tmp1')
        app, freezer, urls = self.freeze_app(tmp_path_1)
        destination = app.config['FREEZER_DESTINATION']
        # Run the freezer on its own output
        tmp_path_2 = tmp_path_factory.mktemp('tmp2')
        app2 = freezer.make_static_app()
        app2.config['FREEZER_DESTINATION'] = tmp_path_2
        app2.debug = True
        freezer2 = Freezer(app2)
        freezer2.register_generator(self.filenames.keys)
        freezer2.freeze()
        assert read_all(destination) == read_all(tmp_path_2)

    def test_error_on_external_url(self, tmp_path):
        urls = ('http://example.com/foo', '//example.com/foo', 'file:///foo')
        for url in urls:
            app, freezer = self.make_app(tmp_path)

            @freezer.register_generator
            def external_url():
                yield url

            try:
                freezer.freeze()
            except ValueError as error:
                assert 'External URLs not supported' in error.args[0]
            else:
                assert False, 'Expected ValueError'

    def test_error_on_internal_404(self, tmp_path):
        app, freezer = self.make_app(tmp_path, with_404=True)
        # Test standard behaviour with 404 errors (freeze failure)
        try:
            freezer.freeze()
        except ValueError as e:
            error_msg = "Unexpected status '404 NOT FOUND' on URL /404/"
            assert error_msg in e.args[0]
        else:
            assert False, 'Expected ValueError'

    def test_warn_on_internal_404(self, tmp_path):
        app, freezer = self.make_app(tmp_path, with_404=True)
        # Enable 404 errors ignoring
        app.config['FREEZER_IGNORE_404_NOT_FOUND'] = True
        # Test warning with 404 errors when we choose to ignore them
        with warns(NotFoundWarning) as logged_warnings:
            warnings.simplefilter('always')
            freezer.freeze()
        assert len(logged_warnings) == 1

    def test_error_on_redirect(self, tmp_path):
        app, freezer = self.make_app(tmp_path)
        # Enable errors on redirects.
        app.config['FREEZER_REDIRECT_POLICY'] = 'error'
        try:
            freezer.freeze()
        except ValueError as e:
            error_msg = "Unexpected status '302 FOUND' on URL /redirect/"
            assert error_msg in e.args[0]
        else:
            assert False, 'Expected ValueError'

    def test_warn_on_redirect(self, tmp_path):
        app, freezer = self.make_app(tmp_path)
        # Enable ignoring redirects.
        app.config['FREEZER_REDIRECT_POLICY'] = 'ignore'
        # Test warning with 302 errors when we choose to ignore them
        with warns(RedirectWarning) as logged_warnings:
            warnings.simplefilter('always')
            freezer.freeze()
        assert len(logged_warnings) == 1

    def test_warn_on_missing_generator(self, tmp_path):
        app, freezer = self.make_app(tmp_path)

        # Add a new endpoint without URL generator
        @app.route('/extra/<some_argument>')
        def external_url(some_argument):
            return some_argument

        with warns(MissingURLGeneratorWarning) as logged_warnings:
            warnings.simplefilter('always')
            freezer.freeze()
        assert len(logged_warnings) == 1

    def test_wrong_default_mimetype(self, tmp_path):
        app, freezer = self.make_app(tmp_path)

        @app.route('/no-file-extension')
        def no_extension():
            return '42', 200, {'Content-Type': 'image/png'}

        with warns(MimetypeMismatchWarning) as logged_warnings:
            warnings.simplefilter('always')
            freezer.freeze()
        assert len(logged_warnings) == 1

    def test_default_mimetype(self, tmp_path):
        app, freezer = self.make_app(tmp_path)

        @app.route('/no-file-extension')
        def no_extension():
            return '42', 200, {'Content-Type': 'application/octet-stream'}

        freezer.freeze()

    def test_unknown_extension(self, tmp_path):
        app, freezer = self.make_app(tmp_path)

        @app.route('/unknown-extension.fuu')
        def no_extension():
            return '42', 200, {'Content-Type': 'application/octet-stream'}

        freezer.freeze()

    def test_configured_default_mimetype(self, tmp_path):
        app, freezer = self.make_app(tmp_path)
        app.config['FREEZER_DEFAULT_MIMETYPE'] = 'image/png'

        @app.route('/no-file-extension')
        def no_extension():
            return '42', 200, {'Content-Type': 'image/png'}

        freezer.freeze()

    def test_wrong_configured_mimetype(self, tmp_path):
        app, freezer = self.make_app(tmp_path)
        app.config['FREEZER_DEFAULT_MIMETYPE'] = 'image/png'

        @app.route('/no-file-extension')
        def no_extension():
            return '42', 200, {'Content-Type': 'application/octet-stream'}

        with warns(MimetypeMismatchWarning) as logged_warnings:
            warnings.simplefilter('always')
            freezer.freeze()
        assert len(logged_warnings) == 1

    def test_skip_existing_files(self, tmp_path):
        app, freezer = self.make_app(tmp_path)
        app.config['FREEZER_SKIP_EXISTING'] = True
        (tmp_path / 'skipped.html').write_text("6*9")

        @app.route('/skipped.html')
        def skipped():
            return '42'

        freezer.freeze()
        assert (tmp_path / 'skipped.html').read_text() == "6*9"

    def test_error_external_redirect(self, tmp_path):
        app, freezer = self.make_app(tmp_path)
        app.config['FREEZER_REDIRECT_POLICY'] = 'follow'

        # Add a new endpoint with external redirect
        @app.route('/redirect/ext/')
        def external_redirected_page():
            return redirect('https://github.com/Frozen-Flask/Frozen-Flask')

        with raises(RuntimeError):
            freezer.freeze()


class TestInitApp(TestFreezer):
    defer_init_app = True


class TestBaseURL(TestFreezer):
    expected_output = TestFreezer.expected_output.copy()
    expected_output['/'] = b'Main index /myapp/product_5/?revision=b12ef20'
    expected_output['/where_am_i/'] = \
        b'/myapp/where_am_i/ http://example/myapp/where_am_i/'
    expected_output['/admin/'] = (
        b'Admin index\n'
        b'<a href="/myapp/page/I%20l%C3%B8v%C3%AB%20Unicode/">'
        b'Unicode test</a>\n'
        b'<a href="/myapp/page/octothorp/?query_foo=bar#introduction">'
        b'URL parsing test</a>')

    def do_extra_config(self, app, freezer):
        app.config['FREEZER_BASE_URL'] = 'http://example/myapp/'


class TestNonexsistentDestination(TestFreezer):
    def do_extra_config(self, app, freezer):
        # frozen/htdocs does not exist in the newly created temp directory,
        # the Freezer has to create it.
        dest = Path(app.config['FREEZER_DESTINATION'])
        app.config['FREEZER_DESTINATION'] = str(dest / 'frozen' / 'htdocs')


class TestServerName(TestFreezer):
    def do_extra_config(self, app, freezer):
        app.config['SERVER_NAME'] = 'example.net'

    expected_output = TestFreezer.expected_output.copy()
    expected_output['/where_am_i/'] = (
        b'/where_am_i/ http://example.net/where_am_i/')


class TestWithoutUrlForLog(TestFreezer):
    freezer_kwargs = {'log_url_for': False}
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
        app.config['FREEZER_STATIC_IGNORE'] = ['*.js']

    expected_output = TestFreezer.expected_output.copy()
    filenames = TestFreezer.filenames.copy()
    del expected_output['/static/main.js']
    del filenames['/static/main.js']


class TestLastModifiedGenerator(TestFreezer):
    def test_generate_last_modified(self, tmp_path):
        # Yield two pages. One is last_modified in the past, and one is
        # last_modified now. The first page should only be written on the first
        # run. The second page should be written on both runs.
        app, freezer = self.make_app(tmp_path)

        @app.route('/time/<when>/')
        def show_time(when):
            return when + datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        @freezer.register_generator
        def view_post():
            timestamp, now = datetime.fromtimestamp(100000), datetime.now()
            yield 'show_time', {'when': 'epoch'}, timestamp
            yield 'show_time', {'when': 'now'}, now

        freezer.freeze()

        first_mtimes = {
            key: (tmp_path / 'time' / key / 'index.html').stat().st_mtime
            for key in ('epoch', 'now')}

        time.sleep(2)

        freezer.freeze()

        second_mtimes = {
            key: (tmp_path / 'time' / key / 'index.html').stat().st_mtime
            for key in ('epoch', 'now')}

        assert first_mtimes['epoch'] == second_mtimes['epoch']
        assert first_mtimes['now'] != second_mtimes['now']


# with_no_argument_rules=False and with_static_files=False are
# not tested as they produce (expected!) warnings
