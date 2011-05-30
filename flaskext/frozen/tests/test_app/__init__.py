# coding: utf8
from flask import Flask, url_for
from flaskext.frozen import Freezer

from .admin import admin_module


def init_app():
    app = Flask(__name__)
    app.register_module(admin_module, url_prefix='/admin')
    freezer = Freezer(app)

    @app.route('/')
    def index():
        return 'Main index'

    @app.route('/page/<name>/')
    def page(name):
        return u'Hello\xa0World! ' + name

    @app.route('/where_am_i/')
    def where_am_i():
        return (url_for('where_am_i') + ' ' +
                url_for('where_am_i', _external=True))

    @app.route('/robots.txt')
    def robots_txt():
        content = 'User-agent: *\nDisallow: /'
        return app.response_class(content, mimetype='text/plain')

    @app.route('/product_<int:product_id>/')
    def product(product_id):
        return 'Product num %i' % product_id

    @freezer.register_generator
    def product():
        # endpoint, values
        yield 'product', {'product_id': 0}
        # Just a `values` dict. The endpoint defaults to the name of the
        # generator function, just like with Flask views
        yield {'product_id': 1}
        # single string: url
        yield '/product_2/'
        
        yield 'page', {'name': u'I løvë Unicode'}
    
    return app, freezer

