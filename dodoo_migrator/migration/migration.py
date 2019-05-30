# -*- coding: utf-8 -*-
# Copyright 2016-2017 Camptocamp SA
# Copyright 2017-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import print_function

import datetime
import logging
import os
import sys

import semver
import yaml
from dodoo import odoo

from .database import MigrationTable
from .exceptions import MigrationErrorGap, MigrationErrorUnfinished, ParseError

try:
    from . import upgradeservice
except ImportError:
    upgradeservice = None

if odoo.release.version_info[0] > 10:
    from odoo import migration
else:
    migration = None

PY3 = sys.version_info[0] == 3
string_type = str if PY3 else basestring  # noqa

BOLD = u"\033[1m"
RESET = u"\033[0m"
GREEN = u"\033[1;32m"
BLUE = u"\033[1;34m"

_logger = logging.getLogger(BOLD + u"DODOO MIGRATOR" + RESET)

MIG_SERVICES = ("odoo", "oca")
MIG_OPERATIONS = (
    "upgrade",
    "install",
    "uninstall",
    "remove",
    "service",
    "pre_scripts",
    "post_scripts",
)

YAML_EXAMPLE = u"""
--- !Migration
version: 0.0.1
app_version: 10.0
upgrade:
- account
install:
- document
uninstall:
- project
remove:  # Only supported since Odoo 10.0
- removed_code

--- !Migration
version: 0.0.2  # nothing to do
app_version: 10.0

--- !Migration
version: 0.9.9  # prepare for migration service
app_version: 10.0
pre_scripts:
- ./migrate/my-pre-script.py
upgrade:
- document

--- !Migration
version: 1.0.0
app_version: 11.0
service: 'odoo'  # ['odoo'|'oca'] Migration provider
upgrade:  # Executed after migration service
- document
post_scripts:  # Executed after migration service
- ./migrate/my-post-script.py

"""

ROOT_LOGGER_LEVEL = logging.getLogger().getEffectiveLevel()


def load_base(db, force_demo=False, status=None, update_module=False):
    odoo.modules.initialize_sys_path()
    with db.cursor() as cr:
        # This is a brand new registry, just created in
        # odoo.modules.registry.Registry.new().
        registry = odoo.registry(cr.dbname)
        graph = odoo.modules.graph.Graph()
        graph.add_module(cr, "base", [])
        report = registry._assertion_report
        if odoo.release.version_info[0] == 8:
            loaded_modules, processed_modules = odoo.modules.loading.load_module_graph(
                cr, graph, status, perform_checks=update_module, report=report
            )
        else:
            loaded_modules, processed_modules = odoo.modules.loading.load_module_graph(
                cr,
                graph,
                status,
                perform_checks=update_module,
                report=report,
                models_to_check=set(),
            )
        registry.setup_models(cr)


class Migration(yaml.YAMLObject):
    """ A single migration defined by a YAML document """

    __slots__ = ("version", "app_version") + MIG_OPERATIONS
    yaml_tag = u"!Migration"

    def __setstate__(self, data):
        """ yaml.load_all does call __setstate__, but not __init__ """
        self.__init__(**data)

    # Note: sets are not json serializable

    def __init__(
        self,
        version=None,
        app_version=None,
        upgrade=None,
        install=None,
        uninstall=None,
        remove=None,
        service=None,
        pre_scripts=None,
        post_scripts=None,
    ):
        self.version = semver.parse_version_info(version)
        self.app_version = app_version
        self.upgrade = self._validate_modules(upgrade, "upgrade")
        self.install = self._validate_modules(install, "install")
        self.uninstall = list(set(uninstall)) if uninstall else []
        self.remove = list(set(remove)) if remove else []
        self.service = self._validate_service(service)
        self.pre_scripts = list(set(pre_scripts)) if pre_scripts else []
        self.post_scripts = list(set(post_scripts)) if post_scripts else []

    @staticmethod
    def _validate_modules(obj, key):
        if obj is None:
            return []
        message = (
            "`{}` key accepts a list of modules that is present in " "addons paths."
        ).format(key)
        if not (obj and all(isinstance(elem, string_type) for elem in obj)):
            raise ParseError(message, YAML_EXAMPLE)
        # TODO: Check if modules are present in source code
        return list(set(obj))

    @staticmethod
    def _validate_service(obj):
        if obj is None:
            return None
        message = "`service` key accepts one of as string: {}".format(
            ", ".join(MIG_SERVICES)
        )
        if obj not in MIG_SERVICES:
            raise ParseError(message, YAML_EXAMPLE)
        return obj

    def _remove(self, cr):
        """ Cleanup module from ir.module.module
        The only use case is, if you completely drop a module without
        replacement. In case of a replacement, include this cleanup into the
        target's migration script or conditional init hoook."""
        if not migration:
            _logger.warning("remove operation is not supported for Odoo < 10.0.")
            return
        for name in self.remove:
            _logger.info(u"migrate to %s (Remove Module: %s).", self.version, name)
            migration.remove_module(cr, name)

    def _run_pre_scripts(self, cr):
        for script in self.pre_scripts:
            _logger.info(u"migrate to %s (Pre Script: %s).", self.version, script)
            exec(open(os.path.abspath(script)).read(), {"cr": cr})

    def _run_odoo_reconciliation(self, cr):
        _load_modules = odoo.modules.load_modules
        odoo.modules.load_modules = load_base
        miniregistry = odoo.registry(cr.dbname)
        uid = odoo.SUPERUSER_ID
        env = odoo.api.Environment(cr, uid, {})
        access_logger = logging.getLogger("odoo.addons.base.models.ir_module")
        access_logger.setLevel(logging.WARNING)
        imm = env["ir.module.module"]
        imm.update_list()
        for name in self.upgrade:
            _logger.info(
                u"migrate to %s (Mark for 'to upgrade': %s).", self.version, name
            )
            imm.search([("name", "=", name)]).button_upgrade()
        for name in self.install:
            _logger.info(
                u"migrate to %s (Mark for 'to install': %s).", self.version, name
            )
            imm.search([("name", "=", name)]).button_install()
        for name in self.uninstall:
            _logger.info(
                u"migrate to %s (Mark for 'to remove': %s).", self.version, name
            )
            imm.search([("name", "=", name)]).button_uninstall()
        access_logger.setLevel(ROOT_LOGGER_LEVEL)
        if odoo.release.version_info[0] <= 9:
            odoo.modules.registry.RegistryManager.delete(cr.dbname)
        else:
            miniregistry.delete(cr.dbname)
        odoo.modules.load_modules = _load_modules
        _logger.info(
            BOLD + BLUE + u"migrate to %s (Odoo Reconciliation Loop: 'to upgrade' / "
            u"'to install' / 'to remove')." + RESET,
            self.version,
        )
        cr.commit()
        try:
            translate_logger = logging.getLogger("odoo.tools.translate")
            translate_logger.setLevel(logging.WARNING)
            fields_logger = logging.getLogger("odoo.fields")
            fields_logger.setLevel(logging.WARNING)
            modules_registry_logger = logging.getLogger("odoo.modules.registry")
            modules_registry_logger.name = (
                BOLD + BLUE + u"odoo.modules.registry" + RESET
            )
            odoo.modules.registry.Registry.new(cr.dbname, update_module="migration")
            modules_registry_logger.name = "odoo.modules.registry"
        except AttributeError:  # Odoo <= 9.0
            translate_logger = logging.getLogger("opernerp.tools.translate")
            translate_logger.setLevel(logging.WARNING)
            fields_logger = logging.getLogger("opernerp.fields")
            fields_logger.setLevel(logging.WARNING)
            modules_registry_logger = logging.getLogger("openerp.modules.registry")
            modules_registry_logger.name = (
                BOLD + BLUE + u"openerp.modules.registry" + RESET
            )
            odoo.modules.registry.RegistryManager.new(
                cr.dbname, update_module="migration"
            )
            modules_registry_logger.name = "openerp.modules.registry"
        finally:
            translate_logger.setLevel(ROOT_LOGGER_LEVEL)
            fields_logger.setLevel(ROOT_LOGGER_LEVEL)

    def _run_post_scripts(self, cr):
        for script in self.post_scripts:
            _logger.info(u"migrate to %s (Post Script: %s).", self.version, script)
            exec(open(os.path.abspath(script)).read(), {"cr": cr})

    def run(self, conn):
        """ Run the actual migration """
        with conn.cursor() as cr:
            self._run_pre_scripts(cr)
        if self.upgrade or self.install or self.uninstall:
            with conn.cursor() as cr:
                self._run_odoo_reconciliation(cr)
        with conn.cursor() as cr:
            self._remove(cr)
        with conn.cursor() as cr:
            self._run_post_scripts(cr)

    def is_noop(self):
        """ Check if Migration is a non operation """
        if not any(getattr(self, a, False) for a in MIG_OPERATIONS):
            return True
        return False


class MigrationSpec(object):
    """ A series of migrations loaded from a yaml file, bound to a database
    coursor. """

    def __init__(self, conn, stream, since, until):
        self.migrations = sorted(
            {mig for mig in yaml.load_all(stream)}, key=lambda m: m.version
        )
        self.mig_table = MigrationTable(conn)
        self.conn = conn
        self.since = since
        self.until = until
        self.versions = sorted(self.mig_table.versions())
        self.finished = {v.number for v in filter(lambda v: v.date_done, self.versions)}
        self.started = {v.number for v in self.versions}
        self.pending = {
            v.number
            for v in filter(lambda v: v.service and not v.date_done, self.versions)
        }

    def _is_applied(self, mig):
        return mig.version in self.finished

    def _get_todo_migrations(self):
        if self.since and self.until:

            def _condition(mig):
                return mig.version > self.since and mig.version <= self.until

        elif self.since:

            def _condition(mig):
                return mig.version > self.since

        elif self.until:

            def _condition(mig):
                return mig.version <= self.until and not self._is_applied(mig)

        else:

            def _condition(mig):
                return not self._is_applied(mig)

        for mig in self.migrations:
            if _condition(mig):
                yield mig

    def run(self):
        """ Execute all applicable migrations from the spec """

        if self.since and self.since <= self.finished[-1]:
            _logger.error(
                "last migration %s not at par with %s.", self.finished[-1], self.since
            )
            raise MigrationErrorGap(self.finished[-1], self.since)

        failed = self.started - self.pending - self.finished
        if failed:
            strfmt = u",".join([str(f) for f in failed])
            _logger.error("migrations %s failed.", strfmt)
            raise MigrationErrorUnfinished(strfmt)

        for mig in self._get_todo_migrations():
            # In case of --since dating to already applied versions
            if self._is_applied(mig):
                _logger.info(
                    BOLD + u"migration %s is already applied - nothing to do." + RESET,
                    mig.version,
                )
                continue

            # Reconcile migrations through service
            if mig.version in self.pending and upgradeservice:
                try:
                    _logger.info(BOLD + u"retrieve from %s." + RESET, mig.service)
                    upgradeservice.db.retrieve(self.conn, mig.service)
                except upgradeservice.errors.NotReadyError:
                    _logger.info(
                        BOLD + u"%s migration not yet ready." + RESET, mig.service
                    )
                    return
            else:
                _logger.info(BOLD + u"start migrating to %s." + RESET, mig.version)
                self.mig_table.start(
                    str(mig.version),
                    mig.app_version,
                    datetime.datetime.now(),
                    mig.service,
                )

            if mig.service and mig.version not in self.pending and upgradeservice:
                _logger.info(BOLD + u"submit to %s for migration." + RESET, mig.service)
                # mode = "test"
                mode = "production"
                upgradeservice.db.submit(self.conn, mig.service, mode, mig.app_version)
                return

            # Apply own migrations
            if mig.is_noop():
                _logger.info(
                    BOLD
                    + u"migration %s is a non operation - only register bump."
                    + RESET,
                    mig.version,
                )
            else:
                mig.run(self.conn)
                _logger.info(
                    BOLD + GREEN + u"finished migrating to %s." + RESET, mig.version
                )

            self.mig_table.finish(
                str(mig.version),
                datetime.datetime.now(),
                {op: getattr(mig, op) for op in MIG_OPERATIONS},
            )
