#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# This file is part of the dodoo-migrator (R) project.
# Copyright (c) 2018 Camptocamp SA and XOE Corp. SAS
# Authors: Guewen Baconnier, Leonardo Pistone, David Arnold, et al.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this library; if not, see <http://www.gnu.org/licenses/>.
#

from __future__ import print_function

import logging
import sys
import threading
import time
from contextlib import contextmanager

import click
import dodoo
import semver
from dodoo import odoo

from . import migration

_logger = logging.getLogger(__name__)


# The number below has been generated as below:
# pg_lock accepts an int8 so we build an hash composed with
# contextual information and we throw away some bits
#     lock_name = 'marabunta'
#     hasher = hashlib.sha1()
#     hasher.update('{}'.format(lock_name))
#     lock_ident = struct.unpack('q', hasher.digest()[:8])
# we just need an integer
ADVISORY_LOCK_IDENT = 7141416871301361999

MIGRATION_SCRIPTS_PATH = None
LOCK = None
LOCK_CR = None


def get_additional_mig_path():
    return MIGRATION_SCRIPTS_PATH


def pg_advisory_lock(cursor, lock_ident):
    cursor.execute("SELECT pg_try_advisory_xact_lock(%s);", (lock_ident,))
    acquired = cursor.fetchone()[0]
    return acquired


class ApplicationLock(threading.Thread):
    def __init__(self, cr):
        self.acquired = False
        self.cr = cr
        self.stop = False
        super(ApplicationLock, self).__init__()

    def run(self):
        # If the migration is run concurrently (in several
        # containers, hosts, ...), only 1 is allowed to proceed
        # with the migration. It will be the first one to win
        # the advisory lock.
        if not pg_advisory_lock(self.cr, ADVISORY_LOCK_IDENT):
            _logger.WARN("A concurrent process is already running the migration")
            sys.exit(1)
        else:
            self.acquired = True
            idx = 0
            while not self.stop:
                # keep the connection alive to maintain the advisory
                # lock by running a query every 30 seconds
                if idx == 60:
                    self.cr.execute("SELECT 1")
                    idx = 0
                idx += 1
                # keep the sleep small to be able to exit quickly
                # when 'stop' is set to True
                time.sleep(0.5)


@contextmanager
def MigrationEnvironment(self):
    conn = odoo.sql_db.db_connect(self.database)
    global LOCK_CR
    LOCK_CR = conn.cursor()
    global LOCK
    LOCK = ApplicationLock(LOCK_CR)
    LOCK.start()
    while not LOCK.acquired:
        time.sleep(0.5)
    with odoo.api.Environment.manage():
        try:
            # we are not in the replica: go on for the migration
            yield conn
        finally:
            LOCK.stop = True
            LOCK.join()
            LOCK_CR.close()
            if odoo.release.version_info[0] < 10:
                odoo.modules.registry.RegistryManager.delete(self.database)
            else:
                odoo.modules.registry.Registry.delete(self.database)
            odoo.sql_db.close_db(self.database)
            odoo.sql_db.close_all()


@click.command(
    cls=dodoo.CommandWithOdooEnv,
    env_options={"environment_manager": MigrationEnvironment},
)
@dodoo.options.addons_path_opt(True)
@dodoo.options.db_opt(True)
@click.option(
    "--file",
    "-f",
    default=".migrations.yaml",
    show_default=True,
    type=click.File("rb", lazy=True),
    help="The yaml file containing the migration steps.",
)
@click.option(
    "--mig-directory",
    "-m",
    type=click.Path(exists=True, file_okay=False),
    help="A migration directory shim. Layout after Odoo's migration"
    "folders within their named module folders."
    "Tipp: Can supply base migration scripts.",
)
@click.option(
    "--since",
    type=semver.VersionInfo.parse,
    required=False,
    help="Specify the version (excluded), to start from. If not "
    "specified, start from the latest applied version onwards.",
)
@click.option(
    "--until",
    type=semver.VersionInfo.parse,
    required=False,
    help="Specify the the target version, to which to migrate. If "
    "not specified, migrate up to the latest version.",
)
@click.option(
    "--metrics/--no-metrics",
    default=False,
    show_default=True,
    help="Prometheus metrics endpoint for migration progress. "
    "Can be consumed by a status page or monitoring solution.",
)
def migrate(env, file, mig_directory, since, until, metrics):
    """ Apply migration paths specified by a descriptive yaml migration file.

    Persists applied migrations within the target database.

    Connects to Odoo SA's migration service and can be run idempotently to
    check for results. Before uploading, can apply special before-steps. Once
    results are avialable, proceeds with remaining migration steps as specified
    by the migration file.

    A prometheus metrics endpoint is instrumented into the script. This can be
    scraped by a monitoring solution or a status page.
    """

    # env is just a Connection object, here

    global MIGRATION_SCRIPTS_PATH
    MIGRATION_SCRIPTS_PATH = mig_directory
    mig_spec = migration.MigrationSpec(env, file, since, until)
    mig_spec.run()


if __name__ == "__main__":  # pragma: no cover
    migrate()
