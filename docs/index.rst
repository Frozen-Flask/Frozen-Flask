Frozen-Flask
============

.. module:: flask_frozen

Frozen-Flask freezes a `Flask`_ application into a set of static files.
The result can be hosted without any server-side software other than a
traditional web server.

.. _Flask: https://palletsprojects.com/p/flask/

Installation
------------

Install the extension with::

    $ pip install Frozen-Flask

or you can get the `source code from GitHub
<https://github.com/Frozen-Flask/Frozen-Flask>`_.

Context
-------

This documentation assumes that you already have a working `Flask`_
application. You can run it and test it with the development server::

    from myapplication import app
    app.run(debug=True)

Frozen-Flask is only about deployment: instead of installing Python,
a WGSI server and Flask on your server, you can use Frozen-Flask to *freeze*
your application and only have static HTML files on your server.

Getting started
---------------

Create a :class:`Freezer` instance with your ``app`` object and call its
:meth:`Freezer.freeze` method. Put that in a ``freeze.py`` script
(or call it whatever you like)::

    from flask_frozen import Freezer
    from myapplication import app

    freezer = Freezer(app)

    if __name__ == '__main__':
        freezer.freeze()

This will create a ``build`` directory next to your application’s ``static``
and ``templates`` directories, with your application’s content frozen into
static files.

.. note::
    Frozen-Flask considers it “owns” its build directory.
    By default, it will **silently overwrite** files in that directory,
    and **remove** those it did not create.

    The `configuration`_ allows you to change the destination directory,
    or control what files are removed if at all.

This build will most likely be partial since Frozen-Flask can only guess so
much about your application.

Finding URLs
------------

Frozen-Flask works by simulating requests at the WSGI level and writing the
responses to aptly named files. So it needs to find out which URLs exist
in your application.

The following URLs can be found automatically:

* Static files handled by Flask for your application or any of its
  `blueprints <https://flask.palletsprojects.com/blueprints/>`_.
* Views with no variable parts in the URL, if they accept the ``GET`` method.
* *New in version 0.6:* Results of calls to :func:`flask.url_for` made by your
  application in the request for another URL.
  In other words, if you use :func:`flask.url_for` to create links in your
  application, these links will be “followed”.

This means that if your application has an index page at the URL ``/``
(without parameters) and every other page can be found from there by
recursively following links built with :func:`flask.url_for`, then
Frozen-Flask can discover all URLs automatically and you’re done.

Otherwise, you may need to write URL generators.

URL generators
--------------

Let’s say that your application looks like this::

    @app.route('/')
    def products_list():
        return render_template('index.html', products=models.Product.all())

    @app.route('/product_<int:product_id>/')
    def product_details(product_id):
        product = models.Product.get_or_404(id=product_id)
        return render_template('product.html', product=product)

If, for some reason, some products pages are not linked from another page
(or these links are not built by :func:`flask.url_for`), Frozen-Flask will
not find them.

To tell Frozen-Flask about them, write a URL generator and put it after
creating your :class:`Freezer` instance and before calling
:meth:`Freezer.freeze`::

    @freezer.register_generator
    def product_details():
        for product in models.Product.all():
            yield {'product_id': product.id}

Frozen-Flask will find the URL by calling ``url_for(endpoint, **values)`` where
``endpoint`` is the name of the generator function and ``values`` is each
dict yielded by the function.

You can specify a different endpoint by yielding a ``(endpoint, values)``
tuple instead of just ``values``, or you can by-pass ``url_for`` and simply
yield URLs as strings.

You can avoid re-freezing URLs by yielding a tuple ``(endpoint, values, time)``,
where ``time`` is a ``datetime.datetime`` object. The URL will only be frozen
if the corresponding output file doesn't exist, or was last modified earlier
than ``time``.

Also, generator functions do not have to be `Python generators
<https://docs.python.org/glossary.html#term-generator>`_ using ``yield``,
they can be any callable and return any iterable object.

All of these are thus equivalent::

    @freezer.register_generator
    def product_details():  # endpoint defaults to the function name
        # `values` dicts
        yield {'product_id': '1'}
        yield {'product_id': '2'}

    @freezer.register_generator
    def product_url_generator():  # Some other function name
        # `(endpoint, values)` tuples
        yield 'product_details', {'product_id': '1'}
        yield 'product_details', {'product_id': '2'}

    @freezer.register_generator
    def product_url_generator():
        # URLs as strings
        yield '/product_1/'
        yield '/product_2/'

    @freezer.register_generator
    def product_url_generator():
        # Return a list. (Any iterable type will do.)
        return [
            '/product_1/',
            # Mixing forms works too.
            ('product_details', {'product_id': '2'}),
        ]

Generating the same URL more than once is okay, Frozen-Flask will build it
only once. Having different functions with the same name is generally a bad
practice, but still work here as they are only used by their decorators.
In practice you will probably have a module for your views and another one
for the freezer and URL generators, so having the same name is not a problem.

Testing URL generators
----------------------

The idea behind Frozen-Flask is that you can `use Flask directly
<#context>`_ to develop and test your application. However, it is
also useful to test your *URL generators* and see that nothing is missing,
before deploying to a production server.

You can open the newly generated static HTML files in a web browser, but
links probably won’t work. The ``FREEZER_RELATIVE_URLS`` `configuration`_
can fix this, but adds a visible ``index.html`` to the links.
Alternatively, use the :meth:`Freezer.run`
method to start an HTTP server on the build result,
so you can check that everything is fine before uploading::

    if __name__ == '__main__':
        freezer.run(debug=True)

:meth:`Freezer.run` will freeze your application before serving and when
the reloader kicks in. But the reloader only watches Python files, not
templates or static files. Because of that, you probably want to use
:meth:`Freezer.run` only for testing the URL generators. For everything
else use the usual :meth:`app.run() <flask.Flask.run>`.

`Flask-Script <https://flask-script.readthedocs.io/>`_ may come in handy
here.

Controlling What Is Followed
----------------------------

Frozen-Flask follows links automatically or with some help from URL generators.
If you want to control what gets followed, then URL generators should be used
with the Freezer's ``with_no_argument_rules`` and ``log_url_for`` flags.
Disabling these flags will force Frozen-Flask to use URL generators only. The
combination of these three elements determines how much Frozen-Flask will
follow.

Configuration
-------------

Frozen-Flask can be configured using Flask’s `configuration system
<https://flask.palletsprojects.com/config/>`_. The following configuration values
are accepted:

``FREEZER_BASE_URL``
    Full URL your application is supposed to be installed at. This affects
    the output of :func:`flask.url_for` for absolute URLs (with
    ``_external=True``) or if your application is not at the root of its
    domain name.
    Defaults to ``'http://localhost/'``.

``FREEZER_RELATIVE_URLS``
    If set to ``True``, Frozen-Flask will patch the Jinja environment so that
    ``url_for()`` returns relative URLs. Defaults to ``False``.
    Python code is not affected unless you use :func:`relative_url_for`
    explicitly. This enables the frozen site to be browsed without a web server
    (opening the files directly in a browser) but appends a visible
    ``index.html`` to URLs that would otherwise end with ``/``.

    .. versionadded:: 0.10

``FREEZER_DEFAULT_MIMETYPE``
    The MIME type that is assumed when it can not be determined from the
    filename extension. If you’re using the Apache web server, this should
    match the ``DefaultType`` value of Apache’s configuration.
    Defaults to ``application/octet-stream``.

    .. versionadded:: 0.7

``FREEZER_IGNORE_MIMETYPE_WARNINGS``
    If set to ``True``, Frozen-Flask won't show warnings if the MIME type
    returned from the server doesn't match the MIME type derived from the
    filename extension. Defaults to ``False``.

    .. versionadded:: 0.8

``FREEZER_DESTINATION``
    Path to the directory where to put the generated static site. If relative,
    interpreted as relative to the application root, next to the ``static`` and
    ``templates`` directories. Defaults to ``build``.

``FREEZER_REMOVE_EXTRA_FILES``
    If set to ``True`` (the default),
    Frozen-Flask will remove files in the destination directory
    that were not built during the current freeze.
    This is intended to clean up files
    generated by a previous call to :meth:`Freezer.freeze`
    that are no longer needed.
    Setting this to ``False`` is equivalent to
    setting ``FREEZER_DESTINATION_IGNORE`` to ``['*']``.

    .. versionadded:: 0.5

``FREEZER_DESTINATION_IGNORE``
    A list (defaults empty) of :mod:`fnmatch` patterns.
    Files or directories in the destination that match any of the patterns
    are not removed,
    even if ``FREEZER_REMOVE_EXTRA_FILES`` is true.
    As in ``.gitignore`` files,
    patterns apply to the whole path if they contain a slash ``/``,
    to each slash-separated part otherwise.
    For example, this could be set to ``['.git*']``
    if the destination is a git repository.

    .. versionadded:: 0.10

``FREEZER_STATIC_IGNORE``
    A list (defaults empty) of :mod:`fnmatch` patterns.
    Files served by send_static_file that match any of the patterns
    are not copied to the build directory.
    As in ``.gitignore`` files,
    patterns apply to the whole path if they contain a slash ``/``,
    to each slash-separated part otherwise.
    For example, this could be set to ``['*.scss']``
    to stop all SASS files from being frozen.

    .. versionadded:: 0.12

``FREEZER_IGNORE_404_NOT_FOUND``
    If set to ``True`` (defaults ``False``), Frozen-Flask won't stop freezing
    when a 404 error is returned by your application.
    In this case, a warning will be printed on stdout and the static page will
    be generated using your 404 error page handler or flask's default one.
    This can be useful during development phase if you have already referenced
    pages which aren't written yet.

    .. versionadded:: 0.12

``FREEZER_REDIRECT_POLICY``
    The policy for handling redirects. This can be:

    * ``'follow'`` (default): when a redirect response is encountered,
      Frozen-Flask will follow it to get the content from the redirected
      location. Note that redirects to external pages are not supported.
    * ``'ignore'``: freezing will continue, but no content will appear in the
      redirecting location.
    * ``'error'`` : raise an exception if a redirect is encountered.

    .. versionadded:: 0.13

``FREEZER_SKIP_EXISTING``
    If set to ``True`` (defaults ``False``), Frozen-Flask will skip the
    generation of files that already exist in the build directory, even if the
    contents would have been different. If set to a function that takes two
    arguments ``url`` and ``filename`` and returns a ``bool``, a file is
    skipped only if the return value of the function is ``True`` when passed
    the URL and on-disk path of the file. Useful if your generation takes up a
    very long time and you want to skip some or all of the existing files.

    .. versionadded:: 0.14

    .. versionadded:: 0.16
       ``FREEZER_SKIP_EXISTING`` now accepts function values.

.. _mime-types:

Filenames and MIME types
------------------------

For each generated URL, Frozen-Flask simulates a request and saves the content
in a file in the ``FREEZER_DESTINATION`` directory. The filename is
built from the URL. URLs with a trailing slash are interpreted as a directory
name and the content is saved in ``index.html``.

Query strings are removed from URLs to build filenames. For example,
``/lorem/?page=ipsum`` is saved to ``lorem/index.html``. URLs that are only
different by their query strings are considered the same, and they should
return the same response. Otherwise, the behavior is undefined.

Additionally, the extension checks that the filename has an extension that
matches the MIME type given in the ``Content-Type`` HTTP response header.
In case of mismatch, the Content-Type that a static web server will send
will probably not be the one you expect, so Frozen-Flask issues a warning.

For example, the following views are both wrong::

    @app.route('/lipsum')
    def lipsum():
        return '<p>Lorem ipsum, ...</p>'

    @app.route('/style.css')
    def compressed_css():
        return '/* ... */'

as the default ``Content-Type`` in Flask is ``text/html; charset=utf-8``, but
the MIME types guessed by the Frozen-Flask as well as most web servers from the
filenames are ``application/octet-stream`` and ``text/css``.

This can be fixed by adding a trailing slash to the URL or serving with the
right ``Content-Type``::

    # Saved as `lipsum/index.html` matches the 'text/html' MIME type.
    @app.route('/lipsum/')
    def lipsum():
        return '<p>Lorem ipsum, ...</p>'

    @app.route('/style.css')
    def compressed_css():
        return '/* ... */', 200, {'Content-Type': 'text/css; charset=utf-8'}

Alternatively, these warnings can be disabled entirely in the configuration_.

Character encodings
-------------------

Flask uses Unicode everywhere internally, and defaults to UTF-8 for I/O.
It will send the right ``Content-Type`` header with both a MIME type and
encoding (eg. ``text/html; charset=utf-8``). Frozen-Flask will try to
`preserve MIME types <#mime-types>`_ through file extensions, but it can not
preserve the encoding meta-data. You may need to add the right
``<meta>`` tag to your HTML. (You should anyway).

Flask also defaults to UTF-8 for URLs, so your web server will get URL-encoded
UTF-8 HTTP requests. It’s up to you to make sure that it converts these to the
native filesystem encoding. Frozen-Flask always writes Unicode filenames.

.. _api:

API reference
-------------

.. autoclass:: Freezer
    :members: init_app, root, register_generator, all_urls, freeze,
              freeze_yield, serve, run

.. autofunction:: walk_directory

.. autofunction:: relative_url_for

Changelog
---------


Version 1.0.0
~~~~~~~~~~~~~

Released on 2023-11-10.

* Support Flask 3.
* Drop support of Python 2 and PyPy.
* Test Python 3.8 to 3.12, and Flask 2 and 3.
* Clean style guide and check it on CI.
* Host documentation on Read the Docs.


Version 0.19
~~~~~~~~~~~~

Released on 2023-11-06.

* Pin Flask < 3 version.


Version 0.18
~~~~~~~~~~~~

Released on 2021-06-15.

* Support Flask 2.
* Ensure that the ``static`` endpoint is emitted by
  ``_static_rules_endpoints`` method with Flask 2.


Version 0.17
~~~~~~~~~~~~

Released on 2021-06-02.

* Allow URL generators to include a ``last_modified`` timestamp to avoid
  generating unmodified pages again.
* Support functions in ``FREEZER_SKIP_EXISTING``.
* Support Python 3.9.
* Launch tests on GitHub Actions.
* Support unquoting URLs that contain multi-byte unicode characters.
* Pin Flask < 2 version.


Version 0.16
~~~~~~~~~~~~

No changes.


Version 0.15
~~~~~~~~~~~~

Released on 2017-06-27.

* Add ``Freezer.freeze_yield()`` method to make progress reporting easier.
  (Thanks to Miro Hrončok.)


Version 0.14
~~~~~~~~~~~~

Released on 2017-03-22.

* Add the ``FREEZER_SKIP_EXISTING`` configuration to skip generation
  of files already in the build directory. (Thanks to Antoine Goutenoir.)
* Add shared superclass ``FrozenFlaskWarning`` for all warnings.
  (Thanks to Miro Hrončok.)


Version 0.13
~~~~~~~~~~~~

Released on 2016-09-30.

* Add the ``FREEZER_REDIRECT_POLICY`` configuration.


Version 0.12
~~~~~~~~~~~~

Released on 2015-11-05.

* Add the ``FREEZER_IGNORE_404_NOT_FOUND`` configuration.
  (Thanks to Thomas Sarboni.)
* Add the ``FREEZER_STATIC_IGNORE`` configuration.
  (Thanks to Alex Guerra.)
* Fix `#36 <https://github.com/Frozen-Flask/Frozen-Flask/issues/36>`_:
  Support non-default app.config['SERVER_NAME'].


Version 0.11
~~~~~~~~~~~~

Released on 2013-06-13.

* Add Python 3.3 support (requires Flask >= 0.10 and Werkzeug >= 0.9)
* Drop Python 2.5 support
* Fix `#30 <https://github.com/Frozen-Flask/Frozen-Flask/issues/30>`_:
  :func:`relative_url_for` with a query string or URL fragment.


Version 0.10
~~~~~~~~~~~~

Released on 2013-03-11.

* Add the ``FREEZER_DESTINATION_IGNORE`` configuration
  (Thanks to Jim Gray and Christopher Roach.)
* Add the ``FREEZER_RELATIVE_URLS`` configuration
* Add the :func:`relative_url_for` function.


Version 0.9
~~~~~~~~~~~

Released on 2012-02-13.

Add :meth:`Freezer.run`.


Version 0.8
~~~~~~~~~~~

Released on 2012-01-17.

* Remove query strings from URLs to build a file names.
  (Should we add configuration to disable this?)
* Raise a warning instead of an exception for `MIME type mismatches
  <#mime-types>`_, and give the option to disable them entirely in the
  configuration.


Version 0.7
~~~~~~~~~~~

Released on 2011-10-20.

* **Backward incompatible change:** Moved the ``flaskext.frozen`` package
  to ``flask_frozen``. You should change your imports either to that or
  to ``flask.ext.frozen`` if you’re using Flask 0.8 or more recent.
  See `Flask’s documentation <https://flask.palletsprojects.com/extensions/>`_
  for details.
* Added FREEZER_DEFAULT_MIMETYPE
* Switch to tox for testing in multiple Python versions


Version 0.6.1
~~~~~~~~~~~~~

Released on 2011-07-29.

Re-release of 0.6 with the artwork included.


Version 0.6
~~~~~~~~~~~

Released on 2011-07-29.

* Thanks to Glwadys Fayolle for the new logo!
* **Frozen-Flask now requires Flask 0.7 or later**. Please use previous
  version of Frozen-Flask if you need previous versions of Flask.
* Support for Flask Blueprints
* Added the ``log_url_for`` parameter to :class:`Freezer`. This makes some
  URL generators unnecessary since more URLs are discovered automatically.
* Bug fixes.


Version 0.5
~~~~~~~~~~~

Released on 2011-07-24.

* You can now construct a Freezer and add URL generators without an app, and
  register the app later with :meth:`Freezer.init_app`.
* The ``FREEZER_DESTINATION`` directory is created if it does not exist.
* New configuration: ``FREEZER_REMOVE_EXTRA_FILES``
* Warn if a URL generator seems to be missing. (ie. if no URL was generated
  for a given endpoint.)
* Write Unicode filenames instead of UTF-8. Non-ASCII filenames are often
  undefined territory anyway.
* Bug fixes.


Version 0.4
~~~~~~~~~~~

Released on 2011-06-02.

* Bugfix: correctly unquote URLs to build filenames. Spaces and non-ASCII
  characters should be %-encoded in URLs but not in frozen filenames. (Web
  servers do the decoding.)
* Add a documentation section about character encodings.


Version 0.3
~~~~~~~~~~~

Released on 2011-05-28.

* URL generators can omit the endpoint and just yield ``values`` dictionaries.
  In that case, the name of the generator function is used as the endpoint,
  just like with Flask views.
* :meth:`Freezer.all_urls` and :func:`walk_directory` are now part of the
  public API.


Version 0.2
~~~~~~~~~~~

Released on 2011-02-21.

Renamed the project from Flask-Static to Frozen-Flask. While we’re at
breaking API compatibility, ``StaticBuilder.build``
is now :func:`Freezer.freeze` and the prefix for configuration
keys is ``FREEZER_`` instead of ``STATIC_BUILDER_``.
Other names were left unchanged.


Version 0.1
~~~~~~~~~~~

Released on 2011-02-06.

First properly tagged release.
