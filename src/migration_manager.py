# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


#
# THIS FILE IS A 1:1 RE IMPLEMENTATION OF THE ODOO MIGRATION MANAGER WITH ONLY
# ONE DIFFERENCE: Allow to *lay over* a migration folder layout.
#

from __future__ import absolute_import, print_function

import glob
import logging
import os
import sys

from dodoo import odoo

from .migrator import get_additional_mig_path

# We need to adopt this strange pattern, as in p27 the import resolution would
# be fooled by the src.odoo package, meant to blend in with the odoo namespace
# from odoo import ... would not use real odoo, but src.odoo in py27
MigrationManager = odoo.modules.migration.MigrationManager  # noqa
parse_version = odoo.tools.parse_version  # noqa

if sys.version_info[0] == 2:
    import imp

    def load_script(path, module_name):
        fp = open(path, "r")
        fname = path
        fp2 = None

        # pylint: disable=file-builtin,undefined-variable
        if not isinstance(fp, file):  # noqa
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


else:
    import importlib.util

    def load_script(path, module_name):
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


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
        def _get_scripts(res, path):
            for version in os.listdir(path):
                if not os.path.isdir(os.path.join(path, version)):
                    continue
                files = glob.glob1(os.path.join(path, version), "*.py")
                files.sort()
                if version not in res:
                    res[version] = [
                        os.path.join(path, version) + os.path.sep + f for f in files
                    ]
                else:
                    res[version].append(
                        [os.path.join(path, version) + os.path.sep + f for f in files]
                    )

        def get_scripts(default, overlay):
            res = {}
            if default:
                _get_scripts(res, default)
            if overlay:
                _get_scripts(res, overlay)
            return res

        for pkg in self.graph:
            if not (
                hasattr(pkg, "update")
                or pkg.state == "to upgrade"  # noqa: W504
                or getattr(pkg, "load_state", None) == "to upgrade"  # noqa: W504
            ):
                continue

            module = get_scripts(
                get_resource_path(pkg.name, "migrations"),
                _get_additional_migration_path(pkg.name, "migrations"),
            )
            maintenance = get_scripts(
                get_resource_path("base", "maintenance", "migrations", pkg.name),
                _get_additional_migration_path(
                    "base", "maintenance", "migrations", pkg.name
                ),
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

            for _, values in migrations.items():
                if version in values:
                    for file in values[version]:
                        if not os.path.basename(file).startswith(stage + "-"):
                            continue
                        lst.append(file)
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
