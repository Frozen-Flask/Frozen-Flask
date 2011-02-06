"""
Flask-Static
------------

Generates a static website from a Flask application. The result can be hosted
without any server-side software other than a traditional web server.

Links
`````

* `documentation <http://packages.python.org/Flask-Static>`_
* `development version
  <http://github.com/SimonSapin/Flask-Static/zipball/master#egg=Flask-Static-dev>`_
"""

from setuptools import setup

setup(
    name='Flask-Static',
    version='0.1',
    url='https://github.com/SimonSapin/Flask-Static',
    license='BSD',
    author='Simon Sapin',
    author_email='simon.sapin@exyr.org',
    description='Generates a static website from a Flask application',
    long_description=__doc__,
    packages=['flaskext'],
    namespace_packages=['flaskext'],
    test_suite='test_flaskstatic',
    zip_safe=False,
    platforms='any',
    install_requires=[
        'Flask',
    ],
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)

