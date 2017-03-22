"""
Frozen-Flask
------------

Freezes a Flask application into a set of static files. The result can be hosted
without any server-side software other than a traditional web server.

Links
`````

* `documentation <http://pythonhosted.org/Frozen-Flask/>`_
* `development version
  <http://github.com/Frozen-Flask/Frozen-Flask/zipball/master#egg=Frozen-Flask-dev>`_
"""

import re
import os.path
from setuptools import setup, find_packages


with open(os.path.join(os.path.dirname(__file__),
                       'flask_frozen', '__init__.py')) as init_py:
    VERSION = re.search("VERSION = '([^']+)'", init_py.read()).group(1)


setup(
    name='Frozen-Flask',
    version=VERSION,
    url='https://github.com/Frozen-Flask/Frozen-Flask',
    license='BSD',
    author='Simon Sapin',
    author_email='simon.sapin@exyr.org',
    description='Freezes a Flask application into a set of static files.',
    long_description=__doc__,
    packages=find_packages(),
    # static files for the test app
    package_data={'': ['static/*', 'admin_static/*', 'templates/*']},
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
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
