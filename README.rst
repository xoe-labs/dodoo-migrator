dodoo-migrator
==============

.. image:: https://img.shields.io/badge/license-LGPL--3-blue.svg
   :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
   :alt: License: LGPL-3
.. image:: https://badge.fury.io/py/dodoo-migrator.svg
    :target: http://badge.fury.io/py/dodoo-migrator

``dodoo-migrator`` is a set of useful Odoo maintenance functions.
They are available as CLI scripts (based on dodoo_), as well
as composable python functions.

.. contents::

Script
~~~~~~
.. code:: bash

  Usage: dodoo-migrator [OPTIONS]

    Apply migration paths specified by a descriptive yaml migration file.

    Persists applied migrations within the target database.

    Connects to Odoo SA's migration service and can be run idempotently to
    check for results. Before uploading, can apply special before-steps. Once
    results are avialable, proceeds with remaining migration steps as
    specified by the migration file.

    A prometheus metrics endpoint is instrumented into the script. This can be
    scraped by a monitoring solution or a status page.

  Options:
    -f, --file FILENAME            The yaml file containing the migration steps.
                                   [default: .migrations.yaml]
    -m, --mig-directory DIRECTORY  A migration directory shim. Layout after
                                   Odoo's migrationfolders within their named
                                   module folders.Tipp: Can supply base
                                   migration scripts.
    --since PARSE                  Specify the version (excluded), to start
                                   from. If not specified, start from the latest
                                   applied version onwards.
    --until PARSE                  Specify the the target version, to which to
                                   migrate. If not specified, migrate up to the
                                   latest version.
    --metrics / --no-metrics       Prometheus metrics endpoint for migration
                                   progress. Can be consumed by a status page or
                                   monitoring solution.  [default: False]
    --logfile FILE                 Specify the log file.
    -d, --database TEXT            Specify the database name. If present, this
                                   parameter takes precedence over the database
                                   provided in the Odoo configuration file.
    --log-level TEXT               Specify the logging level. Accepted values
                                   depend on the Odoo version, and include
                                   debug, info, warn, error.  [default: info]
    -c, --config FILE              Specify the Odoo configuration file. Other
                                   ways to provide it are with the ODOO_RC or
                                   OPENERP_SERVER environment variables, or
                                   ~/.odoorc (Odoo >= 10) or
                                   ~/.openerp_serverrc.
    --help                         Show this message and exit.


Useful links
~~~~~~~~~~~~

- pypi page: https://pypi.org/project/dodoo-migrator
- code repository: https://github.com/xoe-labs/dodoo-migrator
- report issues at: https://github.com/xoe-labs/dodoo-migrator/issues

.. _dodoo: https://pypi.python.org/pypi/dodoo

Credits
~~~~~~~

Contributors:

- Guewen Baconnier (CAMPTOCAMP_)
- Leonardo Pistone (CAMPTOCAMP_)
- David Arnold (XOE_)

.. _CAMPTOCAMP: https://www.camptocamp.com
.. _XOE: https://xoe.solutions

Maintainer
~~~~~~~~~~

.. image:: https://erp.xoe.solutions/logo.png
   :alt: XOE Corp. SAS
   :target: https://xoe.solutions

This project is maintained by XOE Corp. SAS.
