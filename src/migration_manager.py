# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import absolute_import, print_function

import glob
import logging
import os

from click_odoo import odoo

from .migrator import get_additional_mig_path

# We need to adopt this strange pattern, as in p27 the import resolution would
# be fooled by the src.odoo package, meant to blend in with the odoo namespace
# from odoo import ... would not use real odoo, but src.odoo in py27
MigrationManager = odoo.modules.migration.MigrationManager  # noqa
parse_version = odoo.tools.parse_version  # noqa
try:
    load_script = odoo.modules.migration.load_script  # noqa
except AttributeError:
    # Odoo <= 10.0
    import imp

    def load_script(path, module_name):
        fp, fname = odoo.tools.file_open(path, pathinfo=True)
        fp2 = None

        # pylint: disable=file-builtin,undefined-variable
        if not isinstance(fp, file):  # noqa: F821
            # imp.load_source need a real file object, so we create
            # one from the file-like object we get from file_open
            fp2 = os.tmpfile()
            fp2.write(fp.read())
            fp2.seek(0)

        try:
            return imp.load_source(module_name, fname, fp2 or fp)
        finally:
            if fp:
                fp.close()
            if fp2:
                fp2.close()


try:
    get_resource_path = odoo.modules.module.get_resource_path  # noqa
except AttributeError:  # Odoo < 9.0

    get_module_path = odoo.modules.module.get_module_path  # noqa

    def get_resource_path(module, *args):
        """Return the full path of a resource of the given module.
        :param module: module name
        :param list(str) args: resource path components within module
        :rtype: str
        :return: absolute path to the resource
        TODO make it available inside on osv object (self.get_resource_path)
        """
        mod_path = get_module_path(module)
        if not mod_path:
            return False
        resource_path = os.path.join(mod_path, *args)
        if os.path.isdir(mod_path):
            # the module is a directory - ignore zip behavior
            if os.path.exists(resource_path):
                return resource_path
        return False


_logger = logging.getLogger(__name__)


def _get_additional_migration_path(module, *args):
    if not get_additional_mig_path():
        return False
    mod_path = os.path.join(get_additional_mig_path(), module)
    if not mod_path:
        return False
    resource_path = os.path.join(mod_path, *args)
    if os.path.isdir(mod_path):
        # the module is a directory - ignore zip behavior
        if os.path.exists(resource_path):
            return resource_path
    return False


class ExtendedMigrationManager(MigrationManager):
    def _get_files(self):
        def _get_scripts(path):
            if not path:
                return {}
            return {
                version: glob.glob1(os.path.join(path, version), "*.py")
                for version in os.listdir(path)
                if os.path.isdir(os.path.join(path, version))
            }

        for pkg in self.graph:
            if not (
                hasattr(pkg, "update")
                or pkg.state == "to upgrade"  # noqa: W504
                or getattr(pkg, "load_state", None) == "to upgrade"  # noqa: W504
            ):
                continue

            module = _get_scripts(get_resource_path(pkg.name, "migrations"))
            module.update(
                _get_scripts(_get_additional_migration_path(pkg.name, "migrations"))
            )
            maintenance = _get_scripts(
                get_resource_path("base", "maintenance", "migrations", pkg.name)
            )
            maintenance.update(
                _get_scripts(
                    _get_additional_migration_path(
                        "base", "maintenance", "migrations", pkg.name
                    )
                )
            )

            self.migrations[pkg.name] = {"module": module, "maintenance": maintenance}

    def migrate_module(self, pkg, stage):
        assert stage in ("pre", "post", "end")
        stageformat = {"pre": "[>%s]", "post": "[%s>]", "end": "[$%s]"}
        state = (
            pkg.state if stage in ("pre", "post") else getattr(pkg, "load_state", None)
        )

        if (
            not (hasattr(pkg, "update") or state == "to upgrade")
            or state == "to install"
        ):
            return

        def _convert_version(version):
            if version.count(".") >= 2:
                return version  # the version number already containt the server version
            return "{}.{}".format(odoo.release.major_version, version)

        def _get_migration_versions(pkg):
            versions = sorted(
                {
                    ver
                    for lv in self.migrations[pkg.name].values()
                    for ver, lf in lv.items()
                    if lf
                },
                key=lambda k: parse_version(_convert_version(k)),
            )
            return versions

        def _get_migration_files(pkg, version, stage):
            """ return a list of migration script files
            """
            migrations = self.migrations[pkg.name]
            lst = []

            for src in migrations:
                if version in src:
                    for filepath in src[version]:
                        if not os.path.basename(filepath).startswith(stage + "-"):
                            continue
                        lst.append(filepath)
            lst.sort()
            return lst

        installed_version = getattr(pkg, "load_version", pkg.installed_version) or ""
        parsed_installed_version = parse_version(installed_version)
        current_version = parse_version(_convert_version(pkg.data["version"]))

        versions = _get_migration_versions(pkg)

        for version in versions:
            if (
                parsed_installed_version
                < parse_version(_convert_version(version))
                <= current_version
            ):

                strfmt = {
                    "addon": pkg.name,
                    "stage": stage,
                    "version": stageformat[stage] % version,
                }

                for pyfile in _get_migration_files(pkg, version, stage):
                    name, ext = os.path.splitext(os.path.basename(pyfile))
                    if ext.lower() != ".py":
                        continue
                    mod = None
                    try:
                        mod = load_script(pyfile, name)
                        _logger.info(
                            "module %(addon)s: Running migration"
                            " %(version)s %(name)s" % dict(strfmt, name=mod.__name__)
                        )
                        migrate = mod.migrate
                    except ImportError:
                        _logger.exception(
                            "module %(addon)s: Unable to load"
                            "%(stage)s-migration file"
                            "%(file)s" % dict(strfmt, file=pyfile)
                        )
                        raise
                    except AttributeError:
                        _logger.error(
                            "module %(addon)s: Each %(stage)s-"
                            'migration file must have a "migrate(cr,'
                            ' installed_version)" function' % strfmt
                        )
                    else:
                        migrate(self.cr, installed_version)
                    finally:
                        if mod:
                            del mod


odoo.modules.migration.MigrationManager = ExtendedMigrationManager
