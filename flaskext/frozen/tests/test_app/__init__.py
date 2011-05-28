from flask import Flask, url_for
from flaskext.frozen import Freezer

from .admin import admin_module

def product(product_id):
    return 'Product num %i' % product_id

def init_app():
    app = Flask(__name__)
    app.register_module(admin_module, url_prefix='/admin')
    freezer = Freezer(app)

    @app.route('/')
    def index():
        return 'Main index'

    @app.route('/where_am_i/')
    def where_am_i():
        return (url_for('where_am_i') + ' ' +
                url_for('where_am_i', _external=True))

    @app.route('/robots.txt')
    def robots_txt():
        content = 'User-agent: *\nDisallow: /'
        return app.response_class(content, mimetype='text/plain')

    app.route('/product_<int:product_id>/')(product)

    @freezer.register_generator
    def app_urls():
        # endpoint, values
        for id in (0, 1):
            yield 'product', {'product_id': id}
        # single string: url
        yield '/product_2/'
    
    return app, freezer

