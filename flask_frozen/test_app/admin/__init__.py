"""
    flask_frozen.test_app.admin
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Test application Frozen-Flask

    :copyright: (c) 2010-2012 by Simon Sapin.
    :license: BSD, see LICENSE for more details.

"""

from flask import Blueprint

admin_blueprint = Blueprint('admin', __name__,
    static_folder='admin_static', static_url_path='/css')


@admin_blueprint.route('/')
def index():
    return 'Admin index'
