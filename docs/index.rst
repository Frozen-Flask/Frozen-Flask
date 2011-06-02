Frozen-Flask
============

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

Configuration
-------------

To get started all you need to do is to instantiate a :class:`.Freezer` object
after configuring the application::

    from flask import Flask
    from flaskext.frozen import Freezer
    
    app = Flask(__name__)
    app.config.from_pyfile('mysettings.cfg')
    freezer = Freezer(app)

Frozen-Flask accepts the following configuration values:

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
    
URL generators
--------------

The extension work by simulating requests to your application. These requests
are done at the WSGI level. This allow a behavior similar to a real client,
but bypasses the HTTP/TCP/IP stack.

This, the extension needs a list of URLs to request. It can get by with
URL rules that take no arguments and static files (both of which can be
disabled, see :ref:`api`) but you’ll need to help it for everything else.

To do so, register URL generators. A generator is a callable that take no
parameter and return an iterable of URL strings, ``(endpoint, values)``
tuples as for :func:`flask.url_for`, or just a ``values`` dictionary.
In the last case, ``endpoint`` defaults to the name of the generator function,
just like with Flask views.::

    @app.route('/')
    def products_list():
        return render_template('index.html', products=models.Product.all())

    @app.route('/product_<int:product_id>/')
    def product_details():
        product = models.Product.get_or_404(id=product_id)
        return render_template('product.html', product=product)

    @freezer.register_generator
    def product_urls():
        for product in models.Product.all():
            yield 'product_details', {'product_id': product.id}

    # This URL generator is the same as the one above. Generating the same URL
    # more than once is okay, they are de-duplicated.
    @freezer.register_generator
    def product_details():
        for product in models.Product.all():
            # `endpoint` is implicitly the name of the function: product_details
            yield {'product_id': product.id}


Note that the view and the generator have the same name. **TL;DR: that’s okay.**
Having two functions with the same name is generally a bad practice but
causes no problem here as the functions are only used by their decorators.
For non-trivial apps you probably want to have a module for views and
another one for URL generators anyway.

Once everything is configured, run the build::

    if __name__ == '__main__':
        freezer.freeze()

As loading files directly in a web browser does not play well with some URLs,
(browsers do not show ``index.html`` for directories, and absolute path may
have a different meaning, ...) you can also start a server to check that
everything is fine before uploading::

    if __name__ == '__main__':
        freezer.freeze()
        freezer.serve()

`Flask-Script <http://packages.python.org/Flask-Script/>`_ may come in handy
here.

.. _mime-types:

Filenames and MIME types
------------------------

For each generated URL, Frozen-Flask simulates a request and save the content
in a file in the ``FREEZER_DESTINATION`` directory. The filename is
built from the URL. URLs with a trailing slash are interpreted as a directory
name and the content is saved in ``index.html``.

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
``<meta>`` tag to your HTML (you should anyway).

Flask also defaults to UTF-8 for URLs. Since Frozen-Flask chooses the name of
the files it builds from URLs, filenames are UTF-8 too. As links in your HTML
have the same encoding, it should Just Work™. If it doesn’t, please `report
a bug <https://github.com/SimonSapin/Frozen-Flask/issues>`_.

.. _api:

API
---

.. module:: flaskext.frozen

.. autoclass:: Freezer
    :members: register_generator, all_urls, freeze, serve

.. autofunction:: walk_directory

Changelog
---------

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
