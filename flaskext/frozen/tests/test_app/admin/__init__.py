from flask import Blueprint

admin_blueprint = Blueprint('admin', __name__,
    static_folder='admin_static', static_url_path='/css')


@admin_blueprint.route('/')
def index():
    return 'Admin index'
