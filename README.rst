Frozen-Flask
============

Freezes a Flask application into a set of static files. The result can be hosted
without any server-side software other than a traditional web server.

See documentation: https://frozen-flask.readthedocs.io/

Contributing
------------

* Fork the upstream repository and clone your fork
* Create a feature branch for the thing you want to work on
* Create a virtual environment and activate it
* Run ``pip install -e .[doc,test,check]`` to install dependencies
* Add your changes
* Make sure tests pass with ``pytest``
* Make sure you followed the style guide with ``flake8`` and ``isort``
* Send a pull request to the upstream repository

You can also use `Hatch <https://hatch.pypa.io/>`_ to automatically install
dependencies, launch tests, check style and build documentation::

  $ hatch run test:run
  $ hatch run check:run
  $ hatch run doc:build

Status
------

This project is currently maintained by
`CourtBouillon <https://www.courtbouillon.org/>`_.

It’s been previously maintained by
`@honzajavorek <https://github.com/honzajavorek>`_ and
`@tswast <https://github.com/tswast>`_,
and has been originally created by
`@SimonSapin <https://github.com/SimonSapin>`_.

License
-------

Frozen-Flask uses a BSD 3-clause license. See LICENSE.

Copyrights are retained by their contributors, no copyright assignment is
required to contribute to Frozen-Flask. Unless explicitly stated otherwise, any
contribution intentionally submitted for inclusion is licensed under the BSD
3-clause license, without any additional terms or conditions. For full
authorship information, see the version control history.
