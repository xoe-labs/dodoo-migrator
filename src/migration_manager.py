# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from __future__ import print_function

import os
import glob
import logging

from click_odoo import odoo

from odoo.modules.migration import MigrationManager, load_script
from odoo.tools.parse_version import parse_version
from odoo.modules.module import get_resource_path

from .migrator import get_additional_mig_path

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
                version: glob.glob1(os.path.join(path, version), '*.py')
                for version in os.listdir(path)
                if os.path.isdir(os.path.join(path, version))
            }

        for pkg in self.graph:
            if not (hasattr(pkg, 'update') or pkg.state == 'to upgrade' or
                    getattr(pkg, 'load_state', None) == 'to upgrade'):
                continue

            module = _get_scripts(
                get_resource_path(pkg.name, 'migrations'))
            module.update(_get_scripts(
                _get_additional_migration_path(pkg.name, 'migrations')))
            maintenance = _get_scripts(
                get_resource_path(
                    'base', 'maintenance', 'migrations', pkg.name))
            maintenance.update(_get_scripts(
                _get_additional_migration_path(
                    'base', 'maintenance', 'migrations', pkg.name)))

            self.migrations[pkg.name] = {
                'module': module,
                'maintenance': maintenance,
            }

    def migrate_module(self, pkg, stage):
        assert stage in ('pre', 'post', 'end')
        stageformat = {
            'pre': '[>%s]',
            'post': '[%s>]',
            'end': '[$%s]',
        }
        state = pkg.state if stage in ('pre', 'post') else getattr(pkg, 'load_state', None)

        if not (hasattr(pkg, 'update') or state == 'to upgrade') or state == 'to install':
            return

        def _convert_version(version):
            if version.count('.') >= 2:
                return version  # the version number already containt the server version
            return "{}.{}".format(odoo.release.major_version, version)

        def _get_migration_versions(pkg):
            versions = sorted({
                ver
                for lv in self.migrations[pkg.name].values()
                for ver, lf in lv.items()
                if lf
            }, key=lambda k: parse_version(_convert_version(k)))
            return versions

        def _get_migration_files(pkg, version, stage):
            """ return a list of migration script files
            """
            migrations = self.migrations[pkg.name]
            lst = []

            for src in migrations:
                if version in src:
                    for filepath in src[version]:
                        if not os.path.basename(
                                filepath).startswith(stage + '-'):
                            continue
                        lst.append(filepath)
            lst.sort()
            return lst

        installed_version = getattr(
            pkg, 'load_version', pkg.installed_version) or ''
        parsed_installed_version = parse_version(installed_version)
        current_version = parse_version(_convert_version(pkg.data['version']))

        versions = _get_migration_versions(pkg)

        for version in versions:
            if parsed_installed_version < parse_version(
                    _convert_version(version)) <= current_version:

                strfmt = {'addon': pkg.name,
                          'stage': stage,
                          'version': stageformat[stage] % version,
                          }

                for pyfile in _get_migration_files(pkg, version, stage):
                    name, ext = os.path.splitext(os.path.basename(pyfile))
                    if ext.lower() != '.py':
                        continue
                    mod = None
                    try:
                        mod = load_script(pyfile, name)
                        _logger.info(
                            'module %(addon)s: Running migration'
                            ' %(version)s %(name)s' %
                            dict(strfmt, name=mod.__name__))
                        migrate = mod.migrate
                    except ImportError:
                        _logger.exception(
                            'module %(addon)s: Unable to load'
                            '%(stage)s-migration file'
                            '%(file)s' % dict(strfmt, file=pyfile))
                        raise
                    except AttributeError:
                        _logger.error('module %(addon)s: Each %(stage)s-'
                                      'migration file must have a "migrate(cr,'
                                      ' installed_version)" function' % strfmt)
                    else:
                        migrate(self.cr, installed_version)
                    finally:
                        if mod:
                            del mod


odoo.modules.migration.MigrationManager = ExtendedMigrationManager
