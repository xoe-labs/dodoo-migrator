click-odoo-{{ PROJECT }}
==================

.. image:: https://img.shields.io/badge/license-LGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
   :alt: License: LGPL-3
.. image:: https://badge.fury.io/py/click-odoo-.svg
    :target: http://badge.fury.io/py/click-odoo-

``click-odoo-{{ PROJECT }}`` is a set of useful Odoo maintenance functions.
They are available as CLI scripts (based on click-odoo_), as well
as composable python functions.

.. contents::

Script [EXAMPLE - Put output of `--help` here]
~~~~~~
.. code:: bash

  Usage: click-odoo-initdb [OPTIONS]

    Create an Odoo database with pre-installed modules.

    Almost like standard Odoo does with the -i option, except this script
    manages a cache of database templates with the exact same addons
    installed. This is particularly useful to save time when initializing test
    databases.

    Cached templates are identified by computing a sha1 checksum of modules
    provided with the -m option, including their dependencies and
    corresponding auto_install modules.

  Options:
    -c, --config PATH         ...
    ...
    -n, --new-database TEXT   Name of new database to create, possibly from
			      cache. If absent, only the cache trimming
			      operation is executed.
    -m, --modules TEXT        Comma separated list of addons to install.
			      [default: base]
    --demo / --no-demo        Load Odoo demo data.  [default: True]
    --cache / --no-cache      Use a cache of database templates with the exact
			      same addons installed. Disabling this option also
			      disables all other cache-related operations such
			      as max-age or size. Note: when the cache is
			      enabled, all attachments created during database
			      initialization are stored in database instead of
			      the default Odoo file store.  [default: True]
    --cache-prefix TEXT       Prefix to use when naming cache template databases
			      (max 8 characters). CAUTION: all databases named
			      like {prefix}-____________-% will eventually be
			      dropped by the cache control mechanism, so choose
			      the prefix wisely.  [default: cache]
    --cache-max-age INTEGER   Drop cache templates that have not been used for
			      more than N days. Use -1 to disable.  [default:
			      30]
    --cache-max-size INTEGER  Keep N most recently used cache templates. Use -1
			      to disable. Use 0 to empty cache.  [default: 5]
    --help                    Show this message and exit.


Useful links
~~~~~~~~~~~~

- pypi page: https://pypi.org/project/click-odoo-
- code repository: https://github.com//click-odoo-
- report issues at: https://github.com//click-odoo-/issues

.. _click-odoo: https://pypi.python.org/pypi/click-odoo
