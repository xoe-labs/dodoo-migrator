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

# import mock
import os
import subprocess

from click.testing import CliRunner
from click_odoo import odoo

from src.migrator import main

# from ..utils import manifest, gitutils

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "data/test_migrator/")
MIG_TABLE = "click_odoo_migrator"


def _exec_query(dbname, query):
    process = subprocess.Popen(
        ["psql", "-d", dbname, "-t", "-c", query], stdout=subprocess.PIPE
    )
    out, _ = process.communicate()
    return out


def test_mig_sorting(odoodb, odoocfg):
    """ Test if migrations are sorted properly """

    result = CliRunner().invoke(
        main,
        [
            "-d",
            odoodb,
            "-c",
            str(odoocfg),
            "--file",
            DATADIR + ".mig-0.0.x-sorting.yaml",
        ],
    )
    assert result.exit_code == 0
    result = _exec_query(odoodb, "SELECT number FROM {}".format(MIG_TABLE))
    # Assert that log entries are create in the right order.
    assert result == b" 0.0.1\n 0.0.2\n 0.0.3\n\n"


def test_migrator_operations(odoodb, odoocfg):
    """ Test all migrator operations """

    # Test install, upgrade
    result = CliRunner().invoke(
        main,
        [
            "-d",
            odoodb,
            "-c",
            str(odoocfg),
            "--file",
            DATADIR + ".mig-0.1.1-upgrade-install.yaml",
        ],
    )
    assert result.exit_code == 0

    result = _exec_query(
        odoodb, "SELECT state FROM ir_module_module WHERE name='board'"
    )
    # Assert that mail is installed.
    assert result == b" installed\n\n"

    # Test uninstall
    result = CliRunner().invoke(
        main,
        [
            "-d",
            odoodb,
            "-c",
            str(odoocfg),
            "--file",
            DATADIR + ".mig-0.1.2-uninstall.yaml",
        ],
    )
    assert result.exit_code == 0
    result = _exec_query(
        odoodb, "SELECT state FROM ir_module_module WHERE name='board'"
    )
    # Assert that mail is uninstalled.
    assert result == b" uninstalled\n\n"

    if odoo.release.version_info[0] >= 10:
        # Test remove (via odoo.migration package)
        result = CliRunner().invoke(
            main,
            [
                "-d",
                odoodb,
                "-c",
                str(odoocfg),
                "--file",
                DATADIR + ".mig-0.1.3-remove.yaml",
            ],
        )
        assert result.exit_code == 0
        result = _exec_query(
            odoodb, "SELECT 1 FROM ir_module_module WHERE name='board'"
        )
        # Assert board has been removed from module index.
        assert result == b"\n"


def test_database_advisory_lock(odoodb, odoocfg):
    """ Test that no two migrations can accidentially run in parallel """
    pass


def test_migr_folder_overlay(odoodb, odoocfg):
    """ Test if migration folder overlay is workging correctly """
    pass


def test_name_spaced_mig_module(odoodb, odoocfg):
    """ Test if name-spaced odoo module is working properly """
    pass
