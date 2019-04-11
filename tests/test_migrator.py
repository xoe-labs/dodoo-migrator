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

import ast
import os
import subprocess

from click.testing import CliRunner
from dodoo import odoo

from src.migrator import migrate

# from ..utils import manifest, gitutils

HERE = os.path.dirname(__file__)
DATADIR = os.path.join(HERE, "data/test_migrator/")
MIG_TABLE = "dodoo_migrator"
MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py")


def _exec_query(dbname, query):
    process = subprocess.Popen(
        ["psql", "-d", dbname, "-t", "-c", query], stdout=subprocess.PIPE
    )
    out, _ = process.communicate()
    return out


def test_mig_sorting(odoodb, odoocfg):
    """ Test if migrations are sorted properly """

    result = CliRunner().invoke(
        migrate,
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
        migrate,
        [
            "-d",
            odoodb,
            "-c",
            str(odoocfg),
            "--file",
            DATADIR + ".mig-0.1.1-install.yaml",
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
        migrate,
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
            migrate,
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
    """ Test if migration folder overlay is workging correctly and
    upgrade scrips"""
    odoo.tools.config["stop_after_init"] = False
    found = False
    for manifest in MANIFEST_NAMES:
        web_manifest_path = os.path.join(
            odoo.__path__[0], "..", "addons", "web", manifest
        )
        if os.path.isfile(web_manifest_path):
            found = True
            break
    if not found:
        raise

    with open(web_manifest_path, "r") as f:
        old_str = f.read()
        info = ast.literal_eval(old_str)
        info["version"] = "5.0"

    with open(web_manifest_path, "w") as f:
        f.write(str(info))

    with open(web_manifest_path, "r") as f:
        test_str = f.read()

    assert "5.0" in test_str

    result = CliRunner().invoke(
        migrate,
        [
            "-m",
            DATADIR,
            "-d",
            odoodb,
            "-c",
            str(odoocfg),
            "--file",
            DATADIR + ".mig-0.1.4-upgrade.yaml",
        ],
    )
    with open(web_manifest_path, "w") as f:
        f.write(old_str)

    assert result.exit_code == 0

    result_pre = _exec_query(
        odoodb, "SELECT 1 FROM dodoo_test_migrations WHERE name='pre'"
    )
    # Assert pre entry has been written.
    assert result_pre == b"        1\n\n"

    result_post = _exec_query(
        odoodb, "SELECT 1 FROM dodoo_test_migrations WHERE name='post'"
    )
    # Assert post entry has been written.
    assert result_post == b"        1\n\n"

    if odoo.release.version_info[0] <= 8:
        return

    result_end = _exec_query(
        odoodb, "SELECT 1 FROM dodoo_test_migrations WHERE name='end'"
    )
    # Assert end entry has been written.
    assert result_end == b"        1\n\n"


def test_name_spaced_mig_module(odoodb, odoocfg):
    """ Test if name-spaced odoo module is working properly """
    pass
