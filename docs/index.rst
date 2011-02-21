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
parameter and return an iterable of URL strings, or ``(endpoint, values)``
tuples as for :func:`flask.url_for`::

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

.. _api:

API
---

.. module:: flaskext.frozen

.. autoclass:: Freezer
    :members: register_generator, freeze, serve

Changelog
---------

Version 0.2, released 2011-02-21
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Renamed the project from Flask-Static to Frozen-Flask and while we’re at
breaking API compatibility, :func:`flaskext.static.StaticBuilder.build`
is now :func:`flaskext.frozen.Freezer.freeze`. Other function or method names
were left unchanged.

Version 0.2, released 2011-02-06
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

First properly tagged release.
