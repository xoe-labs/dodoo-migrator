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

import os
import subprocess

import pytest
from click.testing import CliRunner
from dodoo import odoo

from dodoo_migrator.cli import migrate

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "data/test_odoo_migration/")
MIG_TABLE = "dodoo_migrator"
MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py")


def _exec_query(dbname, query):
    process = subprocess.Popen(
        ["psql", "-d", dbname, "-t", "-c", query], stdout=subprocess.PIPE
    )
    out, _ = process.communicate()
    return out


def test_all_queries_without_validating_result(odoodb, odoocfg):
    """ Test if all queries are syntax error free. """
    if odoo.release.version_info[0] != 12:
        pytest.skip("version <= 12 all modules / names where taken from v12.")
    # Test install, upgrade
    result = CliRunner().invoke(
        migrate,
        [
            "-d",
            odoodb,
            "-c",
            str(odoocfg),
            "--file",
            DATADIR + ".mig-0.4.0-test-all-queries-syntax.yaml",
        ],
    )
    assert result.exit_code == 0
