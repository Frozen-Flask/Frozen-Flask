from flask import Module

admin_module = Module(__name__, name='admin')


@admin_module.route('/')
def index():
    return 'Admin index'

