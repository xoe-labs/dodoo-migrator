#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# This file is part of the click-odoo-migrator (R) project.
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

import logging

import click
import click_odoo

# from click_odoo import odoo

# from utils import manifest, gitutils

_logger = logging.getLogger(__name__)

# --------- INSTRUCTIONS --------------
# Start building the CLI around main()
# The click-context is enriched to env,
# which behaves like an odoo's self.env
# You might have a look at an example
# click-odoo pproject to get familiar.
# Also, don't forget to consult click's
# excellent docs.
# -------------------------------------


@click.command()
@click_odoo.env_options(default_log_level='warn',
                        with_rollback=False)
@click.option('--file', '-f', default='.migrations.yaml',
              show_default=True, type=click.File('rb', lazy=True),
              help="The yaml file containing the migration steps.")
@click.option('--row/--no-row', default=False, show_default=True,
              help="Run more than one version upgrade at once in a row.")
@click.option('--force', type=str, required=False,
              help="Force upgrade of a version, even if it has already "
                   "been applied. Implies `--row`-flag.")
@click.option('--odoo-upgrade/--no-odoo-upgrade',
              default=False, show_default=True,
              help="Use Odoo SA's upgrade service. "
                   "License code is retrieved from the database itself.")
@click.option('--metrics/--no-metrics',
              default=False, show_default=True,
              help="Expose prometheus metrics endpoint for migration progress. "
                   "Can be consumed by a status page or monitoring solution.")
def main(env, file, row, force, odoo_upgrade):
    """ Apply migration paths specified by a descriptive yaml migration file.

    Persists applied migrations within the target database.

    Connects to Odoo SA's migration service and can be run idempotently to
    check for results. Before uploading, can apply special before-steps. Once
    results are avialable, proceeds with remaining migration steps as specified
    by the migration file.

    A prometheus metrics enpoint is intrumented into the script. This can be
    scraped by a monitoring solution or a status page.
    """

    if force and not row:
        row = True
    pass
if __name__ == '__main__':  # pragma: no cover
    main()
