"""
Frozen-Flask
------------

Freezes a Flask application into a set of static files. The result can be hosted
without any server-side software other than a traditional web server.

Links
`````

* `documentation <http://packages.python.org/Frozen-Flask>`_
* `development version
  <http://github.com/SimonSapin/Frozen-Flask/zipball/master#egg=Frozen-Flask-dev>`_
"""

from setuptools import setup, find_packages

setup(
    name='Frozen-Flask',
    version='0.7',  # Also change this in docs/conf.py
    url='https://github.com/SimonSapin/Frozen-Flask',
    license='BSD',
    author='Simon Sapin',
    author_email='simon.sapin@exyr.org',
    description='Freezes a Flask application into a set of static files.',
    long_description=__doc__,
    packages=find_packages(),
    # static files for the test app
    package_data={'': ['static/*', 'admin_static/*']},
    test_suite='flask_frozen.tests',
    zip_safe=False,
    platforms='any',
    install_requires=[
        'Flask >= 0.7',
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
