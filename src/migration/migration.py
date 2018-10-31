# -*- coding: utf-8 -*-
# Copyright 2016-2017 Camptocamp SA
# Copyright 2017-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import print_function

import datetime
import logging
import sys

import semver
import yaml
from click_odoo import odoo

from .database import MigrationTable
from .exceptions import MigrationErrorGap, MigrationErrorUnfinished, ParseError

if odoo.release.version_info[0] >= 10:
    from ..odoo import migration
else:
    migration = None

PY3 = sys.version_info[0] == 3
string_type = str if PY3 else basestring  # noqa

_logger = logging.getLogger(__name__)

MIG_SERVICES = ("odoo", "oca")
MIG_OPERATIONS = ("upgrade", "install", "uninstall", "remove", "service")

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
upgrade:
- document

--- !Migration
version: 1.0.0
app_version: 11.0
service: 'odoo'  # ['odoo'|'oca'] Migration provider
upgrade:  # Executed after migration service
- document

"""


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
    ):
        self.version = semver.parse_version_info(version)
        self.app_version = app_version
        self.upgrade = self._validate_modules(upgrade, "upgrade")
        self.install = self._validate_modules(install, "install")
        self.uninstall = list(set(uninstall)) if uninstall else []
        self.remove = list(set(remove)) if remove else []
        self.service = self._validate_service(service)

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

    def _mark(self, env):
        """ Mark operations of this migration in the provided environment """
        with env.registry.cursor() as cursor:
            imm = env(cr=cursor)["ir.module.module"]
            for name in self.upgrade:
                imm.search([("name", "=", name)]).button_upgrade()
            for name in self.install:
                imm.search([("name", "=", name)]).button_install()
            for name in self.uninstall:
                imm.search([("name", "=", name)]).button_uninstall()

    def _remove(self, env):
        """ Cleanup module from ir.module.module
        The only use case is, if you completely drop a module without
        replacement. In case of a replacement, include this cleanup into the
        target's migration script or conditional init hoook."""
        if not migration:
            _logger.warning("remove operation is not supported for Odoo < 10.0.")
            return
        for name in self.remove:
            with env.registry.cursor() as cr:
                migration.remove_module(cr, name)

    def run(self, env):
        """ Run the actual migration """
        self._mark(env)
        env.reset()
        try:
            odoo.modules.registry.Registry.new(
                env.registry.db_name, update_module="migration"
            )
        except AttributeError:  # Odoo <= 9.0
            odoo.modules.registry.RegistryManager.new(
                env.registry.db_name, update_module="migration"
            )
        self._remove(env)
        return env

    def is_noop(self):
        """ Check if Migration is a non operation """
        if not any(getattr(self, a, False) for a in MIG_OPERATIONS):
            return True
        return False


class MigrationSpec(object):
    """ A series of migrations loaded from a yaml file, bound to an
    environment. """

    def __init__(self, env, stream, since, until):
        self.migrations = sorted(
            {mig for mig in yaml.load_all(stream)}, key=lambda m: m.version
        )
        self.mig_table = MigrationTable(env)
        self.env = env
        self.since = since
        self.until = until

    def _is_applied(self, mig):
        return mig.version in self._get_finished_vers()

    def _get_finished_vers(self):
        return sorted(
            {
                semver.parse_version_info(v.number)
                for v in self.mig_table.versions()
                if v.date_done
            }
        )

    def _get_unfinished_vers(self):
        return sorted(
            {
                semver.parse_version_info(v.number)
                for v in self.mig_table.versions()
                if not v.date_done
            }
        )

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
        unfinished_v = self._get_unfinished_vers()
        if unfinished_v:
            strfmt = u",".join(unfinished_v)
            _logger.error("migrations %s are in unfinished state.", strfmt)
            raise MigrationErrorUnfinished(strfmt)

        if self.since and self.since not in self._get_finished_vers():
            _logger.error(
                "last migration %s not at par with %s.",
                self._get_finished_vers()[-1],
                self.since,
            )
            raise MigrationErrorGap(self._get_finished_vers()[-1], self.since)

        for mig in self._get_todo_migrations():
            # In case of --since dating to already applied verions
            if self._is_applied(mig):
                _logger.info(
                    u"migration %s is already applied - nothing to do.", (mig.version,)
                )
                continue

            self.mig_table.start(
                str(mig.version), mig.app_version, datetime.datetime.now()
            )

            if mig.is_noop():
                _logger.info(
                    u"migration %s is a non operation - only register bump.",
                    (mig.version,),
                )
            else:
                mig.run(self.env)

            self.mig_table.finish(
                str(mig.version),
                datetime.datetime.now(),
                {op: getattr(mig, op) for op in MIG_OPERATIONS},
            )
