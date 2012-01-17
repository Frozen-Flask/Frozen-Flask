Frozen-Flask
============

.. module:: flask_frozen

Frozen-Flask freezes a `Flask`_ application into a set of static files.
The result can be hosted without any server-side software other than a
traditional web server.

.. _Flask: http://flask.pocoo.org/

**Note:** This project used to be called Flask-Static.

Installation
------------

Install the extension with one of the following commands::

    $ easy_install Frozen-Flask

or alternatively if you have pip installed::

    $ pip install Frozen-Flask

or you can get the `source code from github
<https://github.com/SimonSapin/Frozen-Flask>`_.

Getting started
---------------

Create a :class:`Freezer` instance with you ``app`` object and call its
:meth:`~Freezer.freeze` method. Put that in a ``freeze.py`` script
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
    Frozen-Flask considers it “owns” its build directory. It **will**
    silently overwrite and remove files in that directory.

    If you already have something in ``build``, change the destination
    directory in the `configuration`_.

This build will be most likely be partial since Frozen-Flask can only guess
so much about your application.

Testing your frozen application
-------------------------------

You can open the newly generated static HTML files in a web browser, but
links probably won’t work. To work around this, use the :meth:`~Freezer.serve`
method to start an HTTP server on the build result,
so you can check that everything is fine before uploading::

    if __name__ == '__main__':
        freezer.freeze()
        freezer.serve()

`Flask-Script <http://packages.python.org/Flask-Script/>`_ may come in handy
here.

Finding URLs
------------

Frozen-Flask works by finding which URLs exist in your application, simulating
requests at the WSGI level and writing the responses to aptly named files.

The following URLs can be found automatically:

* Static files handled by Flask for your application or any of its
  `blueprints <http://flask.pocoo.org/docs/blueprints/>`_.
* Views with no variable parts in the URL.
* *New in version 0.6:* Results of calls to :func:`flask.url_for` made by your
  application in the request for another URL.
  In other words, if you use :func:`~flask.url_for` to create links in your
  application, these links will be “followed”.

This means that if your application has an index page at the URL ``/``
(without parameters) and every other page can be found from there by
recursively following links built with :func:`~flask.url_for`, then
Frozen-Flask can discover all URLs automatically and you’re done.

Otherwise, you may need to write URL generators.

URL generators
--------------

Let’s say that your application looks like this::

    @app.route('/')
    def products_list():
        return render_template('index.html', products=models.Product.all())

    @app.route('/product_<int:product_id>/')
    def product_details():
        product = models.Product.get_or_404(id=product_id)
        return render_template('product.html', product=product)

If, for some reason, some products pages are not linked from another page
(or these links are not built by :func:`~flask.url_for`), Frozen-Flask will
not find them.

To tell Frozen-Flask about them, write an URL generator and put it after
creating your :class:`Freezer` instance and before calling
:meth:`~Freezer.freeze`::

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

Also, generator functions do not have to be `Python generators
<http://docs.python.org/glossary.html#term-generator>`_ using ``yield``,
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
In practice you will probably have a module for you views and another one
for the freezer and URL generators, so having the same name is not a problem.

Configuration
-------------

Frozen-Flask can be configured using Flask’s `configuration system
<http://flask.pocoo.org/docs/config/>`_. The following configuration values
are accepted:

``FREEZER_DESTINATION``
    Path to the directory where to put the generated static site. If relative,
    interpreted as relative to the application root, next to the ``static`` and
    ``templates`` directories. Defaults to ``build``.

``FREEZER_BASE_URL``
    Full URL you application is supposed to be installed at. This affects
    the output of :func:`flask.url_for` for absolute URLs (with
    ``_external=True``) or if your application is not at the root of its
    domain name.
    Defaults to ``'http://localhost/'``.

``FREEZER_REMOVE_EXTRA_FILES``
    If set to `True`, Frozen-Flask will remove files in the destination
    directory that were not built during the current freeze. This is intended
    to clean up output files no longer needed on followup calls to
    :meth:`Freezer.freeze`. Defaults to `True`.

    .. versionadded:: 0.5

``FREEZER_DEFAULT_MIMETYPE``
    The MIME type that is assumed when it can not be determined from the
    filename extension. If you’re using the Apache web server, this should
    match the ``DefaultType`` value of Apache’s configuration.
    Defaults to ``application/octet-stream``.

    .. versionadded:: 0.7


``FREEZER_IGNORE_MIMETYPE_WARNINGS``
    If set to `True`, Frozen-Flask won't show warnings if the mimetype
    returned from the server doesn't match the mimetype derived from the
    filename extension.

.. _mime-types:

Filenames and MIME types
------------------------

For each generated URL, Frozen-Flask simulates a request and save the content
in a file in the ``FREEZER_DESTINATION`` directory. The filename is
built from the URL. URLs with a trailing slash are interpreted as a directory
name and the content is saved in ``index.html``.

Query strings are removed from URLs to build filenames. For example,
``/lorem/?page=ipsum`` is saved to ``lorem/index.html``. URLs that are only
different by their query strings are considered the same, and they should
return the same response. Otherwise, the behavior is undefined.

Additionally, the extension checks that the filename has an extension that
match the MIME type given in the ``Content-Type`` HTTP response header.

For example, the following views will both fail::

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

Character encodings
-------------------

Flask uses Unicode everywhere internally, and defaults to UTF-8 for I/O.
It will send the right ``Content-Type`` header with both a MIME type and
and encoding (eg. ``text/html; charset=utf-8``). Frozen-Flask will try to
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
    :members: init_app, register_generator, all_urls, freeze, serve

.. autofunction:: walk_directory

Changelog
---------

Version 0.8, not released yet
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Remove query strings from URLs to build a file names.
  (Should we add configuration to disable this?)


Version 0.7, released on 2011-10-20
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Backward incompatible change:** Moved the ``flaskext.frozen`` package
  to ``flask_frozen``. You should change your imports either to that or
  to ``flask.ext.frozen`` if you’re using Flask 0.8 or more recent.
  See `Flask’s documentation <http://flask.pocoo.org/docs/extensions/>`_
  for details.
* Added FREEZER_DEFAULT_MIMETYPE
* Switch to tox for testing in multiple Python versions


Version 0.6.1, released on 2011-07-29
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Re-release of 0.6 with the artwork included.


Version 0.6, released on 2011-07-29
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Thanks to Glwadys Fayolle for the new logo!
* **Frozen-Flask now requires Flask 0.7 or later**. Please use previous
  version of Frozen-Flask if you need previous versions of Flask.
* Support for Flask Blueprints
* Added the :obj:`log_url_for` parameter to :class:`Freezer`. This makes some
  URL generators unnecessary since more URLs are discovered automatically.
* Bug fixes.


Version 0.5, released on 2011-07-24
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* You can now construct a Freezer and add URL generators without an app, and
  register the app later with :meth:`Freezer.init_app`.
* The ``FREEZER_DESTINATION`` directory is created if it does not exist.
* New configuration: ``FREEZER_REMOVE_EXTRA_FILES``
* Warn if an URL generator seems to be missing. (ie. if no URL was generated
  for a given endpoint.)
* Write Unicode filenames instead of UTF-8. Non-ASCII filenames are often
  undefined territory anyway.
* Bug fixes.


Version 0.4, released on 2011-06-02
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Bugfix: correctly unquote URLs to build filenames. Spaces and non-ASCII
  characters should be %-encoded in URLs but not in frozen filenames. (Web
  servers do the decoding.)
* Add a documentation section about character encodings.


Version 0.3, released on 2011-05-28
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* URL generators can omit the endpoint and just yield ``values`` dictionaries.
  In that case, the name of the generator function is used as the endpoint,
  just like with Flask views.
* :meth:`Freezer.all_urls` and :func:`walk_directory` are now part of the
  public API.


Version 0.2, released on 2011-02-21
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Renamed the project from Flask-Static to Frozen-Flask. While we’re at
breaking API compatibility, :func:`flaskext.static.StaticBuilder.build`
is now :func:`flaskext.frozen.Freezer.freeze` and the prefix for configuration
keys is ``FREEZER_`` instead of ``STATIC_BUILDER_``.
Other names were left unchanged.


Version 0.1, released on 2011-02-06
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First properly tagged release.
