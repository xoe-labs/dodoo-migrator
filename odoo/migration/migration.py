# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import datetime
import imp
import json
import logging
import os
import re
import sys
import time
from collections import namedtuple
from contextlib import contextmanager
from functools import reduce
from inspect import currentframe
from itertools import chain, islice
from operator import itemgetter
from textwrap import dedent

import lxml
import markdown
import psycopg2
from docutils.core import publish_string
from dodoo import odoo
from psycopg2 import sql

from odoo import SUPERUSER_ID, release
from odoo.api import Environment
from odoo.modules.module import get_module_path
from odoo.modules.registry import Registry
from odoo.sql_db import db_connect
from odoo.tools import UnquoteEvalContext
from odoo.tools.func import frame_codeinfo
from odoo.tools.mail import html_sanitize

try:
    from odoo.addons.base.models.ir_module import MyWriter
except ImportError:
    # Odoo < 12.0
    from odoo.addons.base.module.module import MyWriter


_logger = logging.getLogger(__name__)

_INSTALLED_MODULE_STATES = ("installed", "to install", "to upgrade")
IMD_FIELD_PATTERN = "field_%s__%s"

DROP_DEPRECATED_CUSTOM = os.getenv("OE_DROP_DEPRECATED_CUSTOM")

# migration environ, used to share data between scripts
ENVIRON = {}


class MigrationError(Exception):
    pass


# Modules utilities


def modules_installed(cr, *modules):
    """Check if the provided modules are installed (or about to be)."""
    assert modules
    _query = sql.SQL(
        """

        SELECT count(1)
        FROM ir_module_module
        WHERE name IN %(names)s
          AND state IN %(states)s

    """
    )
    cr.execute(_query, dict(names=modules, states=_INSTALLED_MODULE_STATES))
    return cr.fetchone()[0] == len(modules)


def module_installed(cr, module):
    """Check if the provided module is installed (or about to be)."""
    return modules_installed(cr, module)


def remove_module(cr, module):
    """Uninstall the module and delete all its xmlid entries.

    Make sure to reassign records before calling this method.
    """
    # NOTE: we cannot use the uninstall of module because the given
    # module need to be currenctly installed and running as deletions
    # are made using orm.

    _query = sql.SQL(
        """

        SELECT id
        FROM ir_module_module WHERE name = %(module)s

    """
    )
    cr.execute(_query, locals())
    mod_id, = cr.fetchone() or [None]
    if not mod_id:
        return

    # delete constraints only owned by this module
    _query = sql.SQL(
        """

        SELECT name
        FROM ir_model_constraint
        GROUP BY name HAVING array_agg(module) = %(mod_ids)s

    """
    )
    cr.execute(_query, {"mod_ids": [mod_id]})

    constraints = tuple(vals[0] for vals in cr.fetchall())
    if constraints:
        _query = sql.SQL(
            """

            SELECT TABLE_NAME,
                   CONSTRAINT_NAME
            FROM information_schema.table_constraints
            WHERE CONSTRAINT_NAME IN %(constraints)s

        """
        )
        cr.execute(_query, locals())

        for table, constraint in cr.fetchall():
            _params = {
                "table": sql.Identifier(table),
                "constraint": sql.Identifier(constraint),
            }
            _query = sql.SQL(
                """

                ALTER TABLE {table}
                DROP CONSTRAINT {constraint}

            """
            ).format(**_params)
            cr.execute(_query)

    _query = sql.SQL(
        """

        DELETE
        FROM ir_model_constraint
        WHERE module = %(mod_id)s

    """
    )
    cr.execute(_query, locals())

    # delete data
    model_ids, field_ids, view_ids, menu_ids = (), (), (), ()
    _query = sql.SQL(
        """

        SELECT model,
               array_agg(res_id)
        FROM ir_model_data d
        WHERE NOT EXISTS
            (SELECT 1
             FROM ir_model_data
             WHERE id != d.id
               AND res_id = d.res_id
               AND model = d.model
               AND module != d.module)
          AND module = %(module)s
          AND model != 'ir.module.module'
        GROUP BY model

    """
    )
    cr.execute(_query, locals())
    for model, res_ids in cr.fetchall():
        if model == "ir.model":
            model_ids = tuple(res_ids)
        elif model == "ir.model.fields":
            field_ids = tuple(res_ids)
        elif model == "ir.ui.view":
            view_ids = tuple(res_ids)
        elif model == "ir.ui.menu":
            menu_ids = tuple(res_ids)
        else:
            table = table_of_model(cr, model)
            if table_exists(cr, table):
                _params = {"table": sql.Identifier(table)}
                _query = sql.SQL(
                    """

                    DELETE
                    FROM {table}
                    WHERE id IN %(res_ids)s

                """
                ).format(**_params)
                cr.execute(_query, dict(res_ids=tuple(res_ids)))

    for view_id in view_ids:
        remove_view(cr, view_id=view_id, deactivate_custom=True, silent=True)

    if menu_ids:
        remove_menus(cr, menu_ids)

    # remove relations
    _query = sql.SQL(
        """

        SELECT name
        FROM ir_model_relation
        GROUP BY name HAVING array_agg(module) = %(mod_ids)s

    """
    )
    cr.execute(_query, {"mod_ids": [mod_id]})

    relations = tuple(vals[0] for vals in cr.fetchall())

    _query = sql.SQL(
        """

        DELETE
        FROM ir_model_relation
        WHERE module = %(mod_id)s

    """
    )
    cr.execute(_query, locals())
    if relations:
        _query = sql.SQL(
            """

            SELECT TABLE_NAME
            FROM information_schema.tables
            WHERE TABLE_NAME IN %(relations)s

        """
        )
        cr.execute(_query, locals())
        # fmt: on
        for (rel,) in cr.fetchall():
            _params = {"rel": sql.Identifier(rel)}
            _query = sql.SQL(
                """

            DROP TABLE {rel} CASCADE

            """
            ).format(**_params)
            cr.execute(_query)

    if model_ids:
        _query = sql.SQL(
            """

            SELECT model
            FROM ir_model
            WHERE id IN %(model_ids)s

        """
        )
        cr.execute(_query, locals())
        for (model,) in cr.fetchall():
            remove_model(cr, model)

    if field_ids:
        _query = sql.SQL(
            """

            SELECT model,
                   name
            FROM ir_model_fields
            WHERE id IN %(field_ids)s

        """
        )
        cr.execute(_query, locals())
        for model, name in cr.fetchall():
            remove_field(cr, model, name)

    _query = sql.SQL(
        """

        DELETE
        FROM ir_model_data
        WHERE model = 'ir.module.module'
          AND res_id = %(mod_id)s;


        DELETE
        FROM ir_model_data
        WHERE module = %(module)s;


        DELETE
        FROM ir_module_module
        WHERE name = %(module)s;


        DELETE
        FROM ir_module_module_dependency
        WHERE name = %(module)s;

    """
    )
    cr.execute(_query, locals())


def rename_module(cr, old, new):
    """Rename a module. Yes, really."""

    mod_old = "module_" + old
    mod_new = "module_" + new

    _query = sql.SQL(
        """

        UPDATE ir_module_module
        SET name = %(new)s
        WHERE name = %(old)s;


        UPDATE ir_module_module_dependency
        SET name = %(new)s
        WHERE name = %(old)s;


        UPDATE ir_model_data
        SET module = %(new)s
        WHERE module = %(old)s;


        UPDATE ir_model_data
        SET name = %(mod_new)s
        WHERE name = %(mod_old)s
          AND module = 'base'
          AND model = 'ir.module.module';

    """
    )
    cr.execute(_query, locals())


def merge_module(cr, old, into, tolerant=False):
    """Move all references of module `old` into module `into`.

        :param str old: source module to merge
        :param str into: destination module to merge into
        :tolerant bool: if True, the merge will be skipped if the database
                        does not have the `old` module in its ir_module_module
                        table (e.g. if the module was released after the
                        creation of the database)
    """

    _query = sql.SQL(
        """

        SELECT name,
               id
        FROM ir_module_module
        WHERE name IN %(names)s

    """
    )
    cr.execute(_query, dict(names=(old, into)))
    mod_ids = dict(cr.fetchall())

    if tolerant and old not in mod_ids:
        # this can happen in case of temp modules added after a release if the database does not
        # know about this module, i.e: account_full_reconcile in 9.0
        # `into` should be known; let it crash if not
        _logger.warning("Unknow module %s. Skip merging into %s.", old, into)
        return

    def _update(table, old, new):
        _query = sql.SQL(
            """

            UPDATE ir_model_{table} x
            SET module = %(new)s
            WHERE module = %(old)s
              AND NOT EXISTS
                (SELECT 1
                 FROM ir_model_{table} y
                 WHERE y.name = x.name
                   AND y.module = %(new)s)

        """.format(
                table=table
            )
        )
        cr.execute(_query, locals())

        if table == "data":
            _query = sql.SQL(
                """

                SELECT model,
                       array_agg(res_id)
                FROM ir_model_data
                WHERE module = %(old)s
                  AND model NOT LIKE 'ir.model%%'
                GROUP BY model

            """
            )
            cr.execute(_query, locals())
            for model, res_ids in cr.fetchall():
                # we can assume other records have been moved to xml files of the new module
                # remove the unnecessary data and let the module update do its job
                if model == "ir.ui.view":
                    for v in res_ids:
                        remove_view(cr, view_id=v, deactivate_custom=True, silent=True)
                elif model == "ir.ui.menu":
                    remove_menus(cr, tuple(res_ids))
                else:
                    for r in res_ids:
                        remove_record(cr, (model, r))

        _query = sql.SQL(
            """

            DELETE
            FROM ir_model_{table}
            WHERE module = %(old)s

        """.format(
                table=table
            )
        )
        cr.execute(_query, locals())

    _update("constraint", mod_ids[old], mod_ids[into])
    _update("relation", mod_ids[old], mod_ids[into])
    _update_view_key(cr, old, into)
    _update("data", old, into)

    # update dependencies

    _query = sql.SQL(
        """


        INSERT INTO ir_module_module_dependency(module_id, name)
        SELECT module_id,
               %(into)s
        FROM ir_module_module_dependency d
        WHERE name = %(old)s
          AND NOT EXISTS
            (SELECT 1
             FROM ir_module_module_dependency o
             WHERE o.module_id = d.module_id
               AND o.name = %(into)s);


        DELETE
        FROM ir_module_module
        WHERE name = %(old)s;


        DELETE
        FROM ir_module_module_dependency
        WHERE name = %(old)s;

    """
    )
    cr.execute(_query, locals())


def force_install_module(cr, module, deps=None):
    """Force a module to be installed during the upgrade process.

        :param str module: technical name of the module to install
        :param list deps: if set, the module will be installed only if any of
                          module of this list is already installed
                          (or about to be)
    """
    subquery = sql.SQL("")
    if deps:
        subquery = sql.SQL(
            """
            AND EXISTS
              (SELECT 1
               FROM ir_module_module
               WHERE name IN %(deps)s
                 AND state IN %(states)s)

        """
        )
        deps = tuple(deps)
        states = _INSTALLED_MODULE_STATES

    _params = {"subquery": subquery}
    _query = sql.SQL(
        """

         WITH RECURSIVE deps (mod_id, dep_name) AS
          (SELECT m.id,
                  d.name
           FROM ir_module_module_dependency d
           JOIN ir_module_module m ON (d.module_id = m.id)
           WHERE m.name = %(module)s
           UNION SELECT m.id,
                        d.name
           FROM ir_module_module m
           JOIN deps ON deps.dep_name = m.name
           JOIN ir_module_module_dependency d ON (d.module_id = m.id))
        UPDATE ir_module_module m
        SET state = CASE
                        WHEN state = 'to remove' THEN 'to upgrade'
                        WHEN state = 'uninstalled' THEN 'to install'
                        ELSE state
                    END,
                    demo=
          (SELECT demo
           FROM ir_module_module
           WHERE name='base')
        FROM deps d
        WHERE m.id = d.mod_id {subquery} RETURNING m.name,
                                         m.state;

    """
    ).format(**_params)
    cr.execute(_query, locals())
    state = dict(cr.fetchall()).get(module)
    return state


def new_module_dep(cr, module, new_dep):
    """Add a new dependency to a module."""
    # One new dep at a time
    _query = sql.SQL(
        """

        INSERT INTO ir_module_module_dependency(name, module_id)
        SELECT %(new_dep)s,
               id
        FROM ir_module_module m
        WHERE name = %(module)s
          AND NOT EXISTS
            (SELECT 1
             FROM ir_module_module_dependency
             WHERE module_id = m.id
               AND name = %(new_dep)s);

    """
    )
    cr.execute(_query, locals())
    _query = sql.SQL(
        """

        SELECT state
        FROM ir_module_module
        WHERE name = %(module)s;

    """
    )
    cr.execute(_query, locals())

    mod_state = (cr.fetchone() or ["n/a"])[0]
    if mod_state in _INSTALLED_MODULE_STATES:
        # Module was installed, need to install all its deps, recursively,
        # to make sure the new dep is installed
        force_install_module(cr, module)


def remove_module_deps(cr, module, old_deps):
    """Remove a dependencies from a module.
        :param str module: name of the module whose dependencies are removed
        :param tuple old_deps: list of dependencies to be removed
    """
    assert isinstance(old_deps, tuple)
    _query = sql.SQL(
        """

        DELETE
        FROM ir_module_module_dependency
        WHERE module_id =
            (SELECT id
             FROM ir_module_module
             WHERE name = %(module)s)
          AND name IN %(old_deps)s

    """
    )
    cr.execute(_query, locals())


def module_deps_diff(cr, module, add=(), remove=()):
    """Change the dependencies of a module (adding and removing).

        :param str module: technical name of the module with dependency changes
        :param list add: modules to add as dependencies
        :param list remove: modules to remove as dependencies
    """
    for new_dep in add:
        new_module_dep(cr, module, new_dep)
    if remove:
        remove_module_deps(cr, module, tuple(remove))


def new_module(cr, module, deps=(), auto_install=False):
    """Make a new module known to the database.

        :param str module: technical name of the new module
        :param list deps: modules to add as dependencies
        :param bool auto_install: whether the module will auto install if all
                                  its dependencies are installed
    """
    _query = sql.SQL(
        """

        SELECT count(1)
        FROM ir_module_module
        WHERE name = %(module)s

    """
    )
    cr.execute(_query, locals())
    if cr.fetchone()[0]:
        # Avoid duplicate entries for module which is already installed,
        # even before it has become standard module in new version
        # Also happen for modules added afterward, which should be added by multiple series.
        return

    if deps and auto_install:
        state = "to install" if modules_installed(cr, *deps) else "uninstalled"
    else:
        state = "uninstalled"
    _query = sql.SQL(
        """

        INSERT INTO ir_module_module (name, STATE, demo)
        VALUES (%(module)s, %(state)s,
                  (SELECT demo
                   FROM ir_module_module
                   WHERE name='base')) RETURNING id

    """
    )
    cr.execute(_query, locals())
    new_id, = cr.fetchone()

    _query = sql.SQL(
        """

        INSERT INTO ir_model_data (name, module, noupdate, model, res_id)
        VALUES ('module_'||%(module)s,
                                    'base',
                                    't',
                                    'ir.module.module',
                                    %(new_id)s)

    """
    )
    cr.execute(_query, locals())

    for dep in deps:
        new_module_dep(cr, module, dep)


def force_migration_of_fresh_module(cr, module):
    """Force migration scripts to be executed for new modules.

    In some cases, new (or forced installed) modules need a migration script to grab data
    form other modules. In that case, forcing its state to be 'to upgrade' will allow
    migration scripts to be run even if the module was not installed before the migration.
    """
    filename, _ = frame_codeinfo(currentframe(), 1)
    version = ".".join(filename.split(os.path.sep)[-2].split(".")[:2])

    # Force module state to be in `to upgrade`.
    # Needed for migration script execution. See http://git.io/vnF7f
    _query = sql.SQL(
        """

        UPDATE ir_module_module
        SET state = 'to upgrade',
                    latest_version = %(version)s
        WHERE name = %(module)s
          AND state = 'to install' RETURNING id

    """
    )
    cr.execute(_query, locals())
    if cr.rowcount:
        # Force module in `init` mode beside its state is forced to `to upgrade`
        # See http://git.io/vnF7O
        odoo.tools.config["init"][module] = "oh yeah!"


def split_group(cr, from_groups, to_group):
    """Make users members of all `from_groups` members of `to_group`"""

    def check_group(g):
        if isinstance(g, str):
            gid = ref(cr, g)
            if not gid:
                _logger.warning("split_group(): Unknow group: %r", g)
            return gid
        return g

    if not isinstance(from_groups, (list, tuple, set)):
        from_groups = [from_groups]

    from_groups = [g for g in map(check_group, from_groups) if g]
    if not from_groups:
        return

    if isinstance(to_group, str):
        to_group = ref(cr, to_group)

    assert to_group

    _query = sql.SQL(
        """

        INSERT INTO res_groups_users_rel(uid, gid)
        SELECT uid,
               %(to_group)s
        FROM res_groups_users_rel
        GROUP BY uid HAVING array_agg(gid) @> %(from_groups)s EXCEPT
        SELECT uid,
               gid
        FROM res_groups_users_rel
        WHERE gid = %(to_group)s

    """
    )
    cr.execute(_query, locals())


# Models & Fields utilities


def create_m2m(cr, m2m, fk1, fk2, col1=None, col2=None):
    """Create a many2many relation table.

        :param str m2m: relation table name
        :param str fk1: table referenced by first column
        :param str fk2: table referenced by second column
        :param str col1: first column name
        :param str col2: second column name
    """
    if col1 is None:
        col1 = "%s_id" % fk1
    if col2 is None:
        col2 = "%s_id" % fk2

    _params = {
        "m2m": sql.Identifier(m2m),
        "col1": sql.Identifier(col1),
        "fk1": sql.Identifier(fk1),
        "col2": sql.Identifier(col2),
        "fk2": sql.Identifier(fk2),
    }
    _query = sql.SQL(
        """

        CREATE TABLE {m2m}({col1} integer NOT NULL REFERENCES {fk1}(id) ON
                           DELETE CASCADE, {col2} integer NOT NULL REFERENCES {fk2}(id) ON
                           DELETE CASCADE,
                                  UNIQUE ({col1}, {col2}));


        CREATE INDEX ON {m2m}({col1});


        CREATE INDEX ON {m2m}({col2});
    """
    ).format(**_params)
    cr.execute(_query)


def ensure_m2o_func_field_data(cr, src_table, column, dst_table):
    """Fix broken many2one relations.

        If any `column` not present in `dst_table`, remove column from `src_table` in
        order to force recomputation of the function field

        WARN: only call this method on m2o function/related fields!!
    """
    if not column_exists(cr, src_table, column):
        return
    _params = {
        "src_table": sql.Identifier(src_table),
        "column": sql.Identifier(column),
        "dst_table": sql.Identifier(dst_table),
    }
    _query = sql.SQL(
        """
        SELECT count(1)
        FROM {src_table}
        WHERE {column} NOT IN
            (SELECT id
             FROM {dst_table})
    """
    ).format(**_params)
    cr.execute(_query)
    if cr.fetchone()[0]:
        remove_column(cr, src_table, column, cascade=True)


def uniq_tags(cr, model, uniq_column="name", order="id"):
    """Deduplicate "tag" models entries.

        Should only be referenced as many2many

        By using `uniq_column=lower(name)` and `order=name`
        you can prioritize tags in CamelCase/UPPERCASE.
    """
    table = table_of_model(cr, model)
    _upds = sql.SQL("")
    for ft, fc, _, da in get_fk(cr, table):
        assert da == "c"  # should be a ondelete=cascade fk
        cols = get_columns(cr, ft, ignore=(fc,))[0]
        assert len(cols) == 1  # it's a m2, should have only 2 columns

        _params = {
            "rel": sql.Indentifier(ft),
            "c1": sql.Identifier(cols[0]),
            "c2": sql.Identifier(cols[1]),
        }

        _upds += sql.SQL(
            """

            INSERT INTO {rel}({c1}, {c2})
            SELECT r.{c1}, d.id
            FROM {rel} r
            JOIN dups d ON (r.{c2} = ANY(d.others)) EXCEPT
            SELECT r.{c1}, r.{c2}
            FROM {rel} r
            JOIN dups d ON (r.{c2} = d.id)

        """
        ).format(**_params)

    assert _upds  # if not m2m found, there is something wrong...

    # TODO: There is an issue here, find out teleologically, what was meant.
    updates = sql.SQL(", ".join("_upd_%s AS (%s)" % x for x in enumerate(_upds)))
    _params = {
        "table": sql.Identifier(table),
        "uniq_column": sql.Identifier(uniq_column),
        "updates": updates,
    }
    _query = sql.SQL(
        """

         WITH dups AS
          ( SELECT (array_agg(id ORDER BY {order}))[1] AS id,
                   (array_agg(id ORDER BY {order}))[2:array_length(array_agg(id), 1)] AS others
           FROM {table}
           GROUP BY {uniq_column} HAVING count(id) > 1 ), _upd_imd AS
          ( UPDATE ir_model_data x
           SET res_id = d.id
           FROM dups d
           WHERE x.model = %(model)s
             AND x.res_id = ANY(d.others) ), {updates}
        DELETE
        FROM {table}
        WHERE id IN (
          SELECT unnest(others)
          FROM dups)

    """
    ).format(**_params)
    cr.execute(_query, locals())


def remove_field(cr, model, fieldname, cascade=False):
    """Remove a field.

        :param str model: name of the field's model
        :param str fieldname: name of the field (...)
        :param bool cascade: if True, all records having a FKEY pointing to this field
                             will be cascade-deleted (default: False)
    """
    if fieldname == "id":
        # called by `remove_module`. May happen when a model defined in a removed module was
        # overwritten by another module in previous versions.
        return remove_model(cr, model)

    # clean dashboards' `group_by`
    _query = sql.SQL(
        """

        SELECT array_agg(f.name),
               array_agg(aw.id)
        FROM ir_model_fields f
        JOIN ir_act_window aw ON aw.res_model = f.model
        WHERE f.model = %(model)s
          AND f.name = %(fieldname)s
        GROUP BY f.model

    """
    )
    cr.execute(_query, locals())
    for fields, actions in cr.fetchall():
        _query = sql.SQL(
            """

            SELECT id,
                   arch
            FROM ir_ui_view_custom
            WHERE arch ~ %s

        """
        )
        cr.execute(_query, ["name=[\"'](%s)[\"']" % "|".join(map(str, actions))])
        for id, arch in ((x, lxml.etree.fromstring(y)) for x, y in cr.fetchall()):
            for action in arch.iterfind(".//action"):
                context = eval(action.get("context", "{}"), UnquoteEvalContext())
                if context.get("group_by"):
                    context["group_by"] = list(set(context["group_by"]) - set(fields))
                    action.set("context", str(context))
            _query = sql.SQL(
                """

                UPDATE ir_ui_view_custom
                SET arch = %s
                WHERE id = %s

            """
            )
            cr.execute(_query, [lxml.etree.tostring(arch, encoding="unicode"), id])

    _query = sql.SQL(
        """

        DELETE
        FROM ir_model_fields
        WHERE model=%(model)s
          AND name=%(fieldname)s RETURNING id

    """
    )
    cr.execute(_query, locals())
    fids = tuple(vals[0] for vals in cr.fetchall())
    if fids:
        _query = sql.SQL(
            """

            DELETE
            FROM ir_model_data
            WHERE model = 'ir.model.fields'
              AND res_id IN %(fids)s

        """
        )
        cr.execute(_query, locals())

    # cleanup translations
    _query = sql.SQL(
        """

        DELETE
        FROM ir_translation
        WHERE name = %s
          AND TYPE IN ('field',
                       'help',
                       'model',
                       'selection') -- ignore wizard_* translations

    """
    )
    cr.execute(_query, ["{},{}".format(model, fieldname)])

    table = table_of_model(cr, model)
    remove_column(cr, table, fieldname, cascade=cascade)


def move_field_to_module(cr, model, fieldname, old_module, new_module):
    """Move a field to another module."""
    name = IMD_FIELD_PATTERN % (model.replace(".", "_"), fieldname)

    _query = sql.SQL(
        """

        UPDATE ir_model_data
        SET module=%(new_module)s
        WHERE model='ir.model.fields'
          AND name=%(name)s
          AND module=%(old_module)s

    """
    )
    cr.execute(_query, locals())


def rename_field(cr, model, old, new, update_references=True):
    """Rename a module. Yes, really.

        :param bool update_references: if True, references to that field in
                                       filters, saved exports, etc. will be
                                       adapted (default: True)
    """

    _query = sql.SQL(
        """

        UPDATE ir_model_fields
        SET name = %(new)s
        WHERE model = %(model)s
          AND name = %(old)s RETURNING id

    """
    )
    cr.execute(_query, locals())
    [fid] = cr.fetchone() or [None]
    if fid:
        name = IMD_FIELD_PATTERN % (model.replace(".", "_"), new)

        _query = sql.SQL(
            """

            UPDATE ir_model_data
            SET name=%(name)s
            WHERE model='ir.model.fields'
              AND res_id=%(fid)s;


            UPDATE ir_property
            SET name=%(new)s
            WHERE fields_id=%(fid)s;

        """
        )
        cr.execute(_query, locals())
    _query = sql.SQL(
        """


        UPDATE ir_translation
        SET name = %s
        WHERE name = %s
          AND TYPE IN ('field',
                       'help',
                       'model',
                       'selection') -- ignore wizard_* translations

    """
    )
    cr.execute(_query, ["{},{}".format(model, new), "{},{}".format(model, old)])
    table = table_of_model(cr, model)
    # NOTE table_exists is needed to avoid altering views
    if table_exists(cr, table) and column_exists(cr, table, old):
        _params = {
            "table": sql.Identifier(table),
            "old": sql.Identifier(old),
            "new": sql.Identifier(new),
        }
        _query = sql.SQL(
            """

            ALTER TABLE {table} RENAME COLUMN {old} TO {new}

        """
        ).format(**_params)
        cr.execute(_query)

    if update_references:
        update_field_references(cr, old, new, only_models=(model,))


def make_field_company_dependent(
    cr,
    model,
    field,
    field_type,
    target_model=None,
    default_value=None,
    default_value_ref=None,
    company_field="company_id",
):
    """Convert a field to be company dependent (old `property` field attributes).

    Notes:
        `target_model` is only use when `type` is "many2one".
        The `company_field` can be an sql expression.
        You may use `t` to refer the model's table.
    """
    type2field = {
        "char": "value_text",
        "float": "value_float",
        "boolean": "value_integer",
        "integer": "value_integer",
        "text": "value_text",
        "binary": "value_binary",
        "many2one": "value_reference",
        "date": "value_datetime",
        "datetime": "value_datetime",
        "selection": "value_text",
    }

    assert field_type in type2field
    value_field = type2field[field_type]

    _query = sql.SQL(
        """

        SELECT id
        FROM ir_model_fields
        WHERE model = %(model)s
          AND name = %(field)s

    """
    )
    cr.execute(_query, locals())
    [fields_id] = cr.fetchone()

    table = table_of_model(cr, model)

    _params = {
        "field": sql.Identifier(field),
        "value_field": sql.Identifier(value_field),
        "company_field": sql.Identifier(company_field),
        "table": sql.Identifier(table),
        "target_model_prefix": sql.Literal("{},".format(target_model)),
        "model_prefix": sql.Literal("{},".format(model)),
    }

    if default_value is None:
        where_clause = sql.SQL(
            """

            {field} IS NOT NULL

        """
        ).format(**_params)
    else:
        where_clause = sql.SQL(
            """

            {field} != %(default_value)s

        """
        ).format(**_params)

    if field_type != "many2one":
        value_select = sql.Identifier(field)
    else:
        # for m2o, the store value is a reference field, so in format `model,id`
        value_select = sql.SQL(
            """

        CONCAT({target_model_prefix}, {field})

        """
        ).format(**_params)

    _params = dict(
        {"value_select": value_select, "where_clause": where_clause}, **_params
    )
    # TODO: remove me when anonimization module is removed
    if is_field_anonymized(cr, model, field):
        # if field is anonymized, we need to create a property for each record
        where_clause = "true"
        # and we need to unanonymize its values
        ano_default_value = cr.mogrify("%s", [default_value])
        if field_type != "many2one":
            ano_value_select = "%(value)s"
        else:
            ano_value_select = sql.SQL(
                """

            CONCAT({target_model_prefix}, %(value)s)

            """
            ).format(**_params)

        register_unanonymization_query(
            cr,
            model,
            field,
            """
            UPDATE ir_property
               SET {value_field} = CASE WHEN %(value)s IS NULL THEN {ano_default_value}
                                        ELSE {ano_value_select} END
             WHERE res_id = CONCAT({model_prefix}, %(id)s)
               AND name='{field}'
               AND type='{field_type}'
               AND fields_id={fields_id}
            """.format(
                **locals()
            ),
        )

    _query = sql.SQL(
        """

         WITH cte AS
          ( SELECT CONCAT({model_prefix}, id) AS res_id,
                   {value_select} AS value,
                   ({company_field})::integer AS company
           FROM {table} t
           WHERE {where_clause} )
        INSERT INTO ir_property(name, type, fields_id, company_id, res_id, {value_field})
        SELECT %(field)s,
               %(field_type)s,
               %(fields_id)s,
               cte.company,
               cte.res_id,
               cte.value
        FROM cte
        WHERE NOT EXISTS
            (SELECT 1
             FROM ir_property
             WHERE fields_id = %(fields_id)s
               AND COALESCE(company_id, 0) = COALESCE(cte.company, 0)
               AND res_id=cte.res_id)

    """
    ).format(**_params)
    cr.execute(_query, locals())
    # default property
    if default_value:
        _query = sql.SQL(
            """

            INSERT INTO ir_property(name, type, fields_id, {value_field})
            VALUES (%(field)s,
                    %(field_type)s,
                    %(fields_id)s,
                    %(default_value)s) RETURNING id

        """
        )
        cr.execute(_query, locals())
        [prop_id] = cr.fetchone()
        if default_value_ref:
            module, _, xid = default_value_ref.partition(".")

            _query = sql.SQL(
                """

                INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                VALUES (%(module)s,
                        %(xid)s,
                        'ir.property',
                        %(prop_id)s,
                        TRUE)

            """
            )
            cr.execute(_query, locals())

    remove_column(cr, table, field, cascade=True)


def is_field_anonymized(cr, model, field):
    """Check if a field has been anonymized prior to the migration."""
    if not module_installed(cr, "anonymization"):
        return False
    _query = sql.SQL(
        """

        SELECT id
        FROM ir_model_fields_anonymization
        WHERE model_name = %(model)s
          AND field_name = %(field)s
          AND STATE = 'anonymized'

    """
    )
    cr.execute(_query, locals())
    return bool(cr.rowcount)


def update_field_references(cr, old, new, only_models=None):
    """Replaces references to a field in several crash-prone places.

    Replace all references to field `old` to `new` in:
        - ir_filters
        - ir_exports_line
        - ir_act_server
        - ir_rule
        - mail.mass_mailing

        :param list only_models: list of models affected by the fieldname change
    """
    p = {
        "old": r"\y{}\y".format(old),
        "new": new,
        "def_old": r"\ydefault_{}\y".format(old),
        "def_new": "default_{}".format(new),
        "models": tuple(only_models) if only_models else (),
    }

    _query = sql.SQL(
        """

        UPDATE ir_filters
        SET domain = regexp_replace(domain, %(old)s, %(new)s, 'g'),
            context = regexp_replace(regexp_replace(context, %(old)s, %(new)s, 'g'), %(def_old)s, %(def_new)s, 'g')

    """
    )
    if column_exists(cr, "ir_filters", "sort"):
        _query += sql.SQL(", sort = regexp_replace(sort, %(old)s, %(new)s, 'g')")

    if only_models:
        _query += sql.SQL(" WHERE model_id IN %(models)s")

    cr.execute(_query, p)

    # ir.exports.line
    _query = sql.SQL(
        """

        UPDATE ir_exports_line l
        SET name = regexp_replace(l.name, %(old)s, %(new)s, 'g')

    """
    )
    if only_models:
        _query += sql.SQL(
            """

            FROM ir_exports e
            WHERE e.id = l.export_id
              AND e.resource IN %(models)s

        """
        )
    cr.execute(_query, p)

    # ir.action.server
    col_prefix = ""
    if not column_exists(cr, "ir_act_server", "condition"):
        col_prefix = "--"  # sql comment the line
    _query = sql.SQL(
        """

        UPDATE ir_act_server s
        SET {col_prefix} condition = regexp_replace(condition, %(old)s, %(new)s, 'g'),
            code = regexp_replace(code, %(old)s, %(new)s, 'g')

    """.format(
            col_prefix=col_prefix
        )
    )
    if only_models:
        _query += sql.SQL(
            """

            FROM ir_model m
            WHERE m.id = s.model_id
              AND m.model IN %(models)s
              AND

        """
        )
    else:
        _query += sql.SQL(" WHERE ")

    _query += sql.SQL("s.state = 'code'")
    cr.execute(_query, p)

    # ir.rule
    _query = sql.SQL(
        """

        UPDATE ir_rule r
        SET domain_force = regexp_replace(domain_force, %(old)s, %(new)s, 'g')

    """
    )
    if only_models:
        _query += sql.SQL(
            """

            FROM ir_model m
            WHERE m.id = r.model_id
              AND m.model IN %(models)s

        """
        )
    cr.execute(_query, p)

    # mass mailing
    if column_exists(cr, "mail_mass_mailing", "mailing_domain"):
        _query = sql.SQL(
            """

            UPDATE mail_mass_mailing u
            SET mailing_domain = regexp_replace(u.mailing_domain, %(old)s, %(new)s, 'g')

        """
        )
        if only_models:
            if column_exists(cr, "mail_mass_mailing", "mailing_model_id"):
                _query += sql.SQL(
                    """

                    FROM ir_model m
                    WHERE m.id = u.mailing_model_id
                      AND m.model IN %(models)s

                """
                )
            else:
                _query += sql.SQL("WHERE u.mailing_model IN %(models)s")
        cr.execute(_query, p)


def recompute_fields(cr, model, fields, ids=None, logger=_logger, chunk_size=256):
    """Recompute fields using the ORM.

        :param str model:
        :param list fields:
        :param list ids: list of ids of records on which the recompute will be done;
                         if not set, will recompute for all records
        :param logger: logger used during the processing (default: current logger)
        :param integer chunk_size: batch size for recomputing (default: 256)
    """
    if ids is None:
        _params = {"table": sql.Identifier(table_of_model(cr, model))}

        _query = sql.SQL(
            """

            SELECT id FROM {table}

        """
        ).format(**_params)
        cr.execute(_query, locals())
        ids = tuple(map(itemgetter(0), cr.fetchall()))

    Model = env(cr)[model]
    size = (len(ids) + chunk_size - 1) / chunk_size
    qual = "%s %d-bucket" % (model, chunk_size) if chunk_size != 1 else model
    for subids in log_progress(
        chunks(ids, chunk_size, list), qualifier=qual, logger=logger, size=size
    ):
        records = Model.browse(subids)
        for field in fields:
            records._recompute_todo(records._fields[field])
        records.recompute()
        records.invalidate_cache()


def fix_wrong_m2o(cr, table, column, target, value=None):
    """Fix missing foreign keys references.

        :param str table: table to correct
        :param str column: column to correct
        :param str target: destination table of the FKEY
        :param value: value to set instead of the missing foreign key reference
                      that will be parsed by psycopg2 (variable type)
                      (default: None - NULL)
    """
    _params = {
        "table": sql.Identifier(table),
        "target": sql.Identifier(target),
        "column": sql.Identifier(column),
    }
    _query = sql.SQL(
        """

         WITH wrongs_m2o AS
          ( SELECT s.id
           FROM {table} s
           LEFT JOIN {target} t ON s.{column} = t.id
           WHERE s.{column} IS NOT NULL
             AND t.id IS NULL )
        UPDATE {table} s
        SET {column} = %(value)s
        FROM wrongs_m2o w
        WHERE s.id = w.id

    """
    ).format(**_params)
    cr.execute(_query, locals())


def remove_model(cr, model, drop_table=True):
    """Remove a model 😉."""
    model_underscore = model.replace(".", "_")

    # remove references
    for ir in indirect_references(cr):
        if ir.table == "ir_model":
            continue
        _params = {
            "table": sql.Identifier(ir.table),
            "where_clause": sql.SQL(ir.model_filter(placeholder="%(model)s")),
        }
        _query = sql.SQL(
            """

            DELETE
            FROM {table}
            WHERE {where_clause} RETURNING id

        """
        ).format(**_params)
        cr.execute(_query, locals())
        ids = tuple(vals[0] for vals in cr.fetchall())
        remove_refs(cr, model_of_table(cr, ir.table), ids)

    remove_refs(cr, model)

    _query = sql.SQL(
        """

        SELECT id
        FROM ir_model
        WHERE model = %(model)s

    """
    )
    cr.execute(_query, locals())
    [mod_id] = cr.fetchone() or [None]
    if mod_id:
        # some required fk are "ON DELETE SET NULL".
        for tbl in "base_action_rule google_drive_config".split():
            if column_exists(cr, tbl, "model_id"):
                _params = {"tbl": sql.Identifier(tbl)}
                _query = sql.SQL(
                    """

                    DELETE
                    FROM {tbl}
                    WHERE model_id = %(mod_id)s

                """
                ).format(**_params)
                cr.execute(_query, locals())

        _query = sql.SQL(
            """


            DELETE
            FROM ir_model_constraint
            WHERE model=%(mod_id)s;


            DELETE
            FROM ir_model_relation
            WHERE model=%(mod_id)s;

             --- Drop XML IDs of ir.rule and ir.model.access records that will be cascade-dropped,
             --- when the ir.model record is dropped - just in case they need to be re-created

            DELETE
            FROM ir_model_data x USING ir_rule a
            WHERE x.res_id = a.id
              AND x.model='ir.rule'
              AND a.model_id = %(mod_id)s;


            DELETE
            FROM ir_model_data x USING ir_model_access a
            WHERE x.res_id = a.id
              AND x.model='ir.model.access'
              AND a.model_id = %(mod_id)s;


            DELETE
            FROM ir_model
            WHERE id=%(mod_id)s;

        """
        )
        cr.execute(_query, locals())

    _query = sql.SQL(
        """

        DELETE
        FROM ir_model_data
        WHERE model='ir.model'
          AND name = %(name)s;

        DELETE
        FROM ir_model_data
        WHERE model='ir.model.fields'
          AND name LIKE %(name_like)s;

    """
    )
    cr.execute(
        _query,
        dict(
            name="model_{}".format(model_underscore),
            name_like=(IMD_FIELD_PATTERN % (model_underscore, "%")).replace("_", r"\_"),
        ),
    )

    table = table_of_model(cr, model)
    _params = {"table": sql.Identifier(table)}
    if drop_table:
        if table_exists(cr, table):
            _query = sql.SQL(
                """

                DROP TABLE {table} CASCADE

            """
            ).format(**_params)
            cr.execute(_query)
        elif view_exists(cr, table):
            # For auto=False models...
            _query = sql.SQL(
                """

                DROP VIEW {table} CASCADE

            """
            ).format(**_params)
            cr.execute(_query)


def remove_refs(cr, model, ids=None):
    """Remove non-sql enforced references pointing to the specified model.

    e.g. reference fields, translations, ...
    """
    if ids is None:
        match = sql.SQL("like %(needle)s")
        needle = model + ",%"
    else:
        if not ids:
            return
        match = sql.SQL("in %(needle)s")
        needle = tuple("{},{}".format(model, i) for i in ids)

    # "model-comma" fields
    _query = sql.SQL(
        """

        SELECT model,
               name
        FROM ir_model_fields
        WHERE ttype = 'reference'
        UNION
        SELECT 'ir.translation',
               'name'

    """
    )
    cr.execute(_query)

    for ref_model, ref_column in cr.fetchall():
        table = table_of_model(cr, ref_model)
        # NOTE table_exists is needed to avoid deleting from views
        if table_exists(cr, table) and column_exists(cr, table, ref_column):
            _params = {
                "table": sql.Identifier(table),
                "ref_column": sql.Identifier(ref_column),
                "match": match,
            }
            query_tail = sql.SQL(
                """

                FROM {table}
                WHERE {ref_column} {match}

            """
            ).format(**_params)
            if ref_model == "ir.ui.view":
                _query = sql.SQL("""SELECT id """) + query_tail
                cr.execute(_query, locals())
                for (view_id,) in cr.fetchall():
                    remove_view(
                        cr, view_id=view_id, deactivate_custom=True, silent=True
                    )
            elif ref_model == "ir.ui.menu":
                _query = sql.SQL("""SELECT id """) + query_tail
                cr.execute(_query, locals())
                menu_ids = tuple(m[0] for m in cr.fetchall())
                remove_menus(cr, menu_ids)
            else:
                _query = sql.SQL("""DELETE """) + query_tail
                cr.execute(_query, locals())
                # TODO make it recursive?

    if table_exists(cr, "ir_values"):
        column, _ = _ir_values_value(cr)
        _params = {"column": sql.SQL(column), "match": match}

        _query = sql.SQL(
            """

            DELETE
            FROM ir_values
            WHERE {column} {match}

        """
        ).format(**_params)
        cr.execute(_query, locals())

    if ids is None:
        _query = sql.SQL(
            """

            DELETE
            FROM ir_translation
            WHERE name = %(model)s
              AND TYPE IN ('constraint',
                           'sql_constraint',
                           'view',
                           'report',
                           'rml',
                           'xsl')

        """
        )
        cr.execute(_query, locals())


def move_model(cr, model, from_module, to_module, move_data=False, delete=False):
    """Move model `model` from `from_module` to `to_module`.

        :param bool move_data: reassign all xmlids from the `from_module`
                               referencing `model` records to `to_module`
                               (default: False)
        :param bool delete: if True and `to_module` is not installed,
                            delete the model (default: False)
    """
    if delete and not module_installed(cr, to_module):
        remove_model(cr, model)
        return

    model_underscore = model.replace(".", "_")
    name = "model_%s" % model_underscore
    name_like = (IMD_FIELD_PATTERN % (model_underscore, "%")).replace("_", r"\_")
    _query = sql.SQL(
        """

        UPDATE ir_model_data
        SET module = %(to_module)s
        WHERE module = %(from_module)s
          AND model = 'ir.model'
          AND name = %(name)s;


        UPDATE ir_model_data
        SET module = %(to_module)s
        WHERE module = %(from_module)s
          AND model='ir.model.fields'
          AND name LIKE %(name)s;

    """
    )
    cr.execute(_query, locals())

    if move_data:
        _query = sql.SQL(
            """

            UPDATE ir_model_data
            SET module = %(to_module)s
            WHERE module = %(from_module)s
              AND model = %(model)s

        """
        )
        cr.execute(_query, locals())


def rename_model(cr, old, new, rename_table=True):
    """Rename a model.

        :param bool rename_table: if True, the table will be renamed according
                                  to the Odoo ORM (e.g. `ir.rule` -> `ir_rule`)
    """
    if rename_table:
        old_table = table_of_model(cr, old)
        new_table = table_of_model(cr, new)
        _params = {
            "old_table": sql.Identifier(old_table),
            "new_table": sql.Identifier(new_table),
            "old_table_seq_id": sql.Identifier("{}_id_seq".format(old_table)),
            "new_table_sqe_id": sql.Identifier("{}_id_seq".format(new_table)),
        }
        _query = sql.SQL(
            """

            ALTER TABLE {old_table} RENAME TO {new_table};


            ALTER SEQUENCE {old_table_seq_id} RENAME TO {new_table_sqe_id};

        """
        ).format(**_params)
        cr.execute(_query, locals())

        # find & rename primary key, may still use an old name from a former migration
        _query = sql.SQL(
            """

            SELECT conname
            FROM pg_index,
                 pg_constraint
            WHERE indrelid = %(new_table)s::regclass
              AND indisprimary
              AND conrelid = indrelid
              AND conindid = indexrelid
              AND confrelid = 0;

        """
        )
        cr.execute(_query, locals())

        primary_key, = cr.fetchone()

        _params = dict(
            {
                "primary_key": sql.Identifier(primary_key),
                "new_table_pkey": sql.Identifier("{}_pkey".format(new_table)),
            },
            **_params
        )
        _query = sql.SQL(
            """

            ALTER INDEX {primary_key} RENAME TO {new_table_pkey}

        """
        ).format(**_params)
        cr.execute(_query, locals())

        # DELETE all constraints and indexes (ignore the PK), ORM will recreate them.
        _query = sql.SQL(
            """

            SELECT CONSTRAINT_NAME
            FROM information_schema.table_constraints
            WHERE TABLE_NAME = %(new_table)s
              AND constraint_type != 'PRIMARY KEY'
              AND constraint_name !~ '^[0-9_]+_not_null$'

        """
        )
        cr.execute(_query, locals())
        for (constrain,) in cr.fetchall():
            _params = {
                "constrain": sql.Identifier(constrain),
                "new_table": sql.Identifier(new_table),
            }
            _query = sql.SQL(
                """

                DELETE
                FROM ir_model_constraint
                WHERE name = %(constrain)s;


                ALTER TABLE {new_table}
                DROP CONSTRAINT {constrain};

            """
            ).format(**_params)
            cr.execute(_query, locals())

    updates = [r[:2] for r in res_model_res_id(cr)]

    for model, column in updates:
        table = table_of_model(cr, model)
        _params = {"table": sql.Identifier(table), "column": sql.Identifier(column)}
        _query = sql.SQL(
            """

            UPDATE {table}
            SET {column} = %(new)s
            WHERE {column} = %(old)s

        """
        ).format(**_params)
        cr.execute(_query, locals())

    # "model-comma" fields
    _query = sql.SQL(
        """

        SELECT model,
               name
        FROM ir_model_fields
        WHERE ttype = 'reference'
        UNION
        SELECT 'ir.translation',
               'name'

    """
    )
    cr.execute(_query, locals())
    old_like = "{},%".format(old)
    substr_from = len(old)
    for model, column in cr.fetchall():
        table = table_of_model(cr, model)
        if column_exists(cr, table, column):
            _params = {"table": sql.Identifier(table), "column": sql.Identifier(column)}

            _query = sql.SQL(
                """

                UPDATE {table}
                SET {column} = %(new)s || substring({column} FROM %(substr_from)s)
                WHERE {column} LIKE %(old_like)s

            """
            ).format(**_params)
            cr.execute(_query, locals())

    if table_exists(cr, "ir_values"):
        column_read, cast_write = _ir_values_value(cr)
        _params = {
            "cast0": sql.SQL(cast_write.partition("%s")[0]),
            "cast2": sql.SQL(cast_write.partition("%s")[2]),
            "column": sql.SQL(column_read),
        }

        _query = sql.SQL(
            """

            UPDATE ir_values
            SET value = {cast0}%(new)s || substring({column} FROM %(substr_from)s){cast2}
            WHERE {column} LIKE %(old_like)s

        """
        ).format(**_params)
        cr.execute(_query, locals())

    old_underscore = old.replace(".", "_")
    new_underscore = new.replace(".", "_")
    new_name = "model_%s" % new_underscore
    old_name = "model_%s" % old_underscore
    new_field_name = "field_%s" % new_underscore
    old_field_prefix_length = len(old_underscore) + 6
    name_like = (IMD_FIELD_PATTERN % (old_underscore, "%")).replace("_", r"\_")
    _query = sql.SQL(
        """

        UPDATE ir_translation
        SET name = %(new)s
        WHERE name = %(old)s
          AND TYPE IN ('constraint',
                       'sql_constraint',
                       'view',
                       'report',
                       'rml',
                       'xsl');


        UPDATE ir_model_data
        SET name = %(new_name)s
        WHERE model = 'ir.model'
          AND name = %(old_name)s;


        UPDATE ir_model_data
        SET name = %(new_field_name)s || substring(name FROM %(old_field_prefix_length)s)
        WHERE model = 'ir.model.fields'
          AND name LIKE %(name_like)s;

    """
    )
    cr.execute(_query, locals())

    col_prefix = ""
    if not column_exists(cr, "ir_act_server", "condition"):
        col_prefix = "--"  # sql comment the line

    _params = {
        "col_prefix": sql.SQL(col_prefix),
        "old": sql.SQL(old),
        "new": sql.SQL(new),
    }
    _query = sql.SQL(
        r"""

        UPDATE ir_act_server
        -- regex matching model name wrapped by quotes eg in env['model.name'] or env["model.name"]
        SET {col_prefix} condition = regexp_replace(condition, '([''"]){old}\1', '\1{new}\1', 'g'),
                                   code = regexp_replace(code, '([''"]){old}\1', '\1{new}\1', 'g')
    """
    ).format(**_params)
    cr.execute(_query, locals())


def replace_record_references(cr, old, new, replace_xmlid=True):
    """Replace all (in)direct references of a record by another"""
    assert isinstance(old, tuple) and len(old) == 2
    assert isinstance(new, tuple) and len(new) == 2

    if not old[1]:
        return

    return replace_record_references_batch(
        cr, {old[1]: new[1]}, old[0], new[0], replace_xmlid
    )


def replace_record_references_batch(
    cr, id_mapping, model_src, model_dst=None, replace_xmlid=True
):
    assert id_mapping
    assert all(isinstance(v, int) and isinstance(k, int) for k, v in id_mapping.items())

    if model_dst is None:
        model_dst = model_src

    old = tuple(id_mapping.keys())
    new = tuple(id_mapping.values())
    jmap = json.dumps(id_mapping)

    def genmap(fmt_k, fmt_v=None):
        # generate map using given format
        fmt_v = fmt_k if fmt_v is None else fmt_v
        m = {fmt_k % k: fmt_v % v for k, v in id_mapping.items()}
        return json.dumps(m), tuple(m.keys())

    if model_src == model_dst:
        # 7 time faster than using pickle.dumps
        pmap, pmap_keys = genmap("I%d\n.")
        smap, smap_keys = genmap("%d")

        column_read, cast_write = _ir_values_value(cr)

        for table, fk, _, _ in get_fk(cr, table_of_model(cr, model_src)):
            _params = {"table": sql.Identifier(table), "fk": sql.Identifier(fk)}

            jmap_query = sql.SQL(
                """

                UPDATE {table} t
                SET {fk} = (%(jmap)s::json->>{fk}::varchar)::int4
                WHERE {fk} IN %(old)s

            """
            ).format(**_params)

            col2 = None
            if not column_exists(cr, table, "id"):
                # seems to be a m2m table. Avoid duplicated entries
                cols = get_columns(cr, table, ignore=(fk,))[0]
                assert len(cols) == 1  # it's a m2, should have only 2 columns
                col2 = cols[0]
                _params = {
                    "table": sql.Identifier(table),
                    "fk": sql.Identifier(fk),
                    "col2": sql.Identifier(col2),
                    "jmap_query": jmap_query,
                }

                _query = sql.SQL(
                    """

                     WITH _existing AS
                      ( SELECT {col2}
                       FROM {table}
                       WHERE {fk} IN %(new)s ) {jmap_query}
                    AND NOT EXISTS
                      (SELECT 1
                       FROM _existing
                       WHERE {col2}=t.{col2});


                    DELETE
                    FROM {table} WHERE {fk} IN %(old)s;

                """
                ).format(**_params)
                cr.execute(_query, locals())

            if not col2:  # it's a model
                # update default values
                # TODO? update all defaults using 1 query (using `WHERE (model, name) IN ...`)
                model = model_of_table(cr, table)
                if table_exists(cr, "ir_values"):
                    _params = {
                        "cast0": sql.SQL(cast_write.partition("%s")[0]),
                        "cast2": sql.SQL(cast_write.partition("%s")[2]),
                        "column": sql.Identifier(column_read),
                    }

                    _query = sql.SQL(
                        """

                        UPDATE ir_values
                        SET value = {cast0} %(pmap)s::json->>({column}) {cast2}
                        WHERE KEY='default'
                          AND model = %(model)s
                          AND name = %(fk)s
                          AND {column} IN %(pmap_keys)s

                    """
                    ).format(**_params)
                    cr.execute(_query, locals())
                else:
                    _query = sql.SQL(
                        """

                        UPDATE ir_default d
                        SET json_value = %(smap)s::json->>json_value
                        FROM ir_model_fields f
                        WHERE f.id = d.field_id
                          AND model = %(model)s
                          AND name = %(fk)s
                          AND d.json_value IN %(pmap_keys)s

                    """
                    )
                    cr.execute(_query, locals())

    # indirect references
    for ir in indirect_references(cr, bound_only=True):
        if ir.table == "ir_model_data" and not replace_xmlid:
            continue
        _params = {}
        upd = sql.SQL("")
        if ir.res_model:
            _params["model"] = sql.Identifier(ir.res_model)
            upd += sql.SQL("{model} = %(model_dst)s,").format(**_params)
        if ir.res_model_id:
            _params["model_id"] = sql.Identifier(ir.res_model_id)
            upd += sql.SQL(
                "{model_id} = (SELECT id FROM ir_model WHERE model = %(model_dst)s),"
            ).format(**_params)
        where = sql.SQL(ir.model_filter(placeholder="%(model_src)s"))

        _params = dict(
            {
                "table": sql.Identifier(ir.table),
                "res_id": sql.Identifier(ir.res_id),
                "upd": upd,
                "where": where,
            },
            **_params
        )

        _query = sql.SQL(
            """

            UPDATE {table}
            SET {upd} {res_id} = (%(jmap)s::json->>{res_id}::varchar)::int4
            WHERE {where}
              AND {res_id} IN %(old)s

        """
        ).format(**_params)
        cr.execute(_query, locals())

    # reference fields
    cmap, cmap_keys = genmap("%s,%%d" % model_src, "%s,%%d" % model_dst)
    cr.execute("SELECT model, name FROM ir_model_fields WHERE ttype='reference'")
    for model, column in cr.fetchall():
        table = table_of_model(cr, model)
        if column_exists(cr, table, column):
            _params = {"table": sql.Identifier(table), "column": sql.Identifier(column)}

            _query = sql.SQL(
                """

                UPDATE {table}
                SET {column} = %(cmap)s::json->>{column}
                WHERE {column} IN %(cmap_keys)s

            """
            ).format(**_params)
            cr.execute(_query, locals())


# ---------- UI Utilities (Views, Menus) ----------
def _update_view_key(cr, old, new):
    """Update the key of a view."""
    if not column_exists(cr, "ir_ui_view", "key"):
        return

    _query = sql.SQL(
        """


        UPDATE ir_ui_view v
        SET key = CONCAT(%(new)s, '.', x.name)
        FROM ir_model_data x
        WHERE x.model = 'ir.ui.view'
          AND x.res_id = v.id
          AND x.module = %(old)s
          AND v.key = CONCAT(x.module, '.', x.name)

    """
    )
    cr.execute(_query, locals())


def remove_view(
    cr,
    xml_id=None,
    view_id=None,
    deactivate_custom=DROP_DEPRECATED_CUSTOM,
    silent=False,
):
    """
    Recursively delete the given view and its inherited views.

    Delete the view and its inherited views as long as they are part of a module.
    Will crash as soon as a custom view exists anywhere
    in the hierarchy.

        :param xml_id=None: fully qualified xmlid of the view
        :param view_id=None: id of the view
        :param deactivate_custom=False: if set, any custom view inheriting from
                                        any of the deleted views will be
                                        deactivated, otherwise a MigrationError
                                        will be raised if a custom view exists;
                                        can be set by the system environment
                                        variable OE_DROP_DEPRECATED_CUSTOM
        :param silent=False: if True, no log output will be generated

    Note that you can either provide an xml_id or view_id but not both.
    """
    assert bool(xml_id) ^ bool(view_id), "You Must specify either xmlid or view_id"
    if xml_id:
        view_id = ref(cr, xml_id)
        if not view_id:
            return

        module, _, name = xml_id.partition(".")
        _query = sql.SQL(
            """

            SELECT model
            FROM ir_model_data
            WHERE module = %(module)s
              AND name = %(name)s

        """
        )
        cr.execute(_query, locals())

        [model] = cr.fetchone()
        if model != "ir.ui.view":
            raise ValueError(
                "{!r} should point to a 'ir.ui.view', not a {!r}".format(xml_id, model)
            )
    elif not silent or deactivate_custom:
        # search matching xmlid for logging or renaming of custom views

        _query = sql.SQL(
            """

            SELECT module,
                   name
            FROM ir_model_data
            WHERE model='ir.ui.view'
              AND res_id = %(view_id)s

        """
        )
        cr.execute(_query, locals())
        if cr.rowcount:
            xml_id = "%s.%s" % cr.fetchone()
        else:
            xml_id = None

    _query = sql.SQL(
        """


        SELECT v.id,
               x.module || '.' || x.name
        FROM ir_ui_view v
        LEFT JOIN ir_model_data x ON ( v.id = x.res_id
                                      AND x.model = 'ir.ui.view'
                                      AND x.module !~ '^_' )
        WHERE v.inherit_id = %(view_id)s

    """
    )
    cr.execute(_query, locals())
    for child_id, child_xml_id in cr.fetchall():
        if child_xml_id:
            if not silent:
                _logger.info(
                    "Dropping deprecated built-in view %s (ID %s), "
                    "as parent %s (ID %s) is going to be removed",
                    child_xml_id,
                    child_id,
                    xml_id,
                    view_id,
                )
            remove_view(
                cr, child_xml_id, deactivate_custom=deactivate_custom, silent=True
            )
        else:
            if deactivate_custom:
                if not silent:
                    _logger.warning(
                        "Deactivating deprecated custom view with "
                        "ID %s, as parent %s (ID %s) was removed",
                        child_id,
                        xml_id,
                        view_id,
                    )
                disable_view_query = sql.SQL(
                    """

                    UPDATE ir_ui_view
                    SET name = (name || ' - old view, inherited from ' || %(xml_id)s),
                        model = (model || '.disabled'),
                        inherit_id = NULL
                    WHERE id = %(child_id)s

                """
                )
                cr.execute(disable_view_query, locals())
            else:
                raise MigrationError(
                    "Deprecated custom view with ID %s needs migration, "
                    "as parent %s (ID %s) is going to be removed"
                    % (child_id, xml_id, view_id)
                )
    if not silent:
        _logger.info("Dropping deprecated built-in view %s (ID %s).", xml_id, view_id)
    if xml_id:
        remove_record(cr, xml_id)


@contextmanager
def edit_view(cr, xmlid=None, view_id=None, skip_if_noupdate=False):
    """Contextmanager that may yield etree arch of a view.

    As it may not yield, you must use `skippable_cm`:

    with migration.skippable_cm(), migration.edit_view(cr, 'xmlid') as arch:
        arch.attrib['string'] = 'My Form'

        :param xml_id=None: fully qualified xmlid of the view
        :param view_id=None: id of the view
        :param skip_if_noupdate=False: if True, will not yield if the view is
                                       set to be non-updatable

    Note that you can either provide an xml_id or view_id but not both.
    """
    assert bool(xmlid) ^ bool(view_id), "You Must specify either xmlid or view_id"
    noupdate = True
    if xmlid:
        if "." not in xmlid:
            raise ValueError("Please use fully qualified name <module>.<name>")

        module, _, name = xmlid.partition(".")

        _query = sql.SQL(
            """

            SELECT res_id,
                   noupdate
            FROM ir_model_data
            WHERE module = %(module)s
              AND name = %(name)s

        """
        )
        cr.execute(_query, locals())
        data = cr.fetchone()
        if data:
            view_id, noupdate = data

    if view_id and not (skip_if_noupdate and noupdate):
        _query = sql.SQL(
            """

            SELECT arch_db
            FROM ir_ui_view
            WHERE id = %(view_id)s

        """
        )
        cr.execute(_query, locals())
        [arch] = cr.fetchone() or [None]
        if arch:
            arch = lxml.etree.fromstring(arch)
            yield arch
            arch = lxml.etree.tostring(arch, encoding="unicode")
            _query = sql.SQL(
                """

                UPDATE ir_ui_view
                SET arch_db = %(arch)s
                WHERE id = %(view_id)s

            """
            )
            cr.execute(_query, locals())


def remove_menus(cr, menu_ids):
    """Remove ir.ui.menu records with the provided ids (and their children)."""
    if not menu_ids:
        return
    menu_ids = tuple(menu_ids)
    _query = sql.SQL(
        """

         WITH RECURSIVE tree(id) AS
          ( SELECT id
           FROM ir_ui_menu
           WHERE id IN %(menu_ids)s
           UNION SELECT m.id
           FROM ir_ui_menu m
           JOIN tree t ON (m.parent_id = t.id) )
        DELETE
        FROM ir_ui_menu m USING tree t
        WHERE m.id = t.id RETURNING m.id

    """
    )
    cr.execute(_query, locals())
    ids = tuple(x[0] for x in cr.fetchall())
    if ids:
        _query = sql.SQL(
            """

            DELETE
            FROM ir_model_data
            WHERE model='ir.ui.menu'
              AND res_id IN %(ids)s

        """
        )
        cr.execute(_query, locals())


# ---------- Database/Postgres Utilities ----------


def dbuuid(cr):
    """Get the uuid of the current database.

    In the case of a duplicated database, return the original uuid."""

    _query = sql.SQL(
        """

        SELECT value
        FROM ir_config_parameter
        WHERE KEY IN ('database.uuid',
                      'origin.database.uuid')
        ORDER BY KEY DESC LIMIT 1

    """
    )
    cr.execute(_query, locals())
    return cr.fetchone()[0]


def has_enterprise():
    """Check if the current installation has enterprise addons availables or not."""
    return bool(
        get_module_path("web_enterprise", downloaded=False, display_warning=False)
    )


def model_of_table(cr, table):
    """Return the model name for the provided table."""
    return {
        # could also be ir.actions.act_window_close, but we have yet
        # to encounter a case where we need it
        "ir_actions": "ir.actions.actions",
        "ir_act_url": "ir.actions.act_url",
        "ir_act_window": "ir.actions.act_window",
        "ir_act_window_view": "ir.actions.act_window.view",
        "ir_act_client": "ir.actions.client",
        "ir_act_report_xml": "ir.actions.report",
        "ir_act_server": "ir.actions.server",
        "ir_act_wizard": "ir.actions.wizard",
        "ir_config_parameter": "ir.config_parameter",
    }.get(table, table.replace("_", "."))


def table_of_model(cr, model):
    """Return the table for the provided model name."""
    return {
        "ir.actions.actions": "ir_actions",
        "ir.actions.act_url": "ir_act_url",
        "ir.actions.act_window": "ir_act_window",
        "ir.actions.act_window_close": "ir_actions",
        "ir.actions.act_window.view": "ir_act_window_view",
        "ir.actions.client": "ir_act_client",
        "ir.actions.report.xml": "ir_act_report_xml",
        "ir.actions.report": "ir_act_report_xml",
        "ir.actions.server": "ir_act_server",
        "ir.actions.wizard": "ir_act_wizard",
    }.get(model, model.replace(".", "_"))


def table_exists(cr, table):
    """Check if the specified table exists."""
    _query = sql.SQL(
        """

        SELECT 1
        FROM information_schema.tables
        WHERE table_name = %(table)s
          AND table_type = 'BASE TABLE'

    """
    )
    cr.execute(_query, locals())
    return cr.fetchone() is not None


def column_exists(cr, table, column):
    """Check if the column exist on the specified table."""
    return column_type(cr, table, column) is not None


def column_type(cr, table, column):
    """Get the type of the column on the specified table."""
    _query = sql.SQL(
        """

        SELECT udt_name
        FROM information_schema.columns
        WHERE table_name = %(table)s
          AND column_name = %(column)s

    """
    )
    cr.execute(_query, locals())
    r = cr.fetchone()
    return r[0] if r else None


def create_column(cr, table, column, definition):
    """Create a column on the specified table.

        :param str table: name of the table on which the column will be created
        :param str column: name of the new column
        :param str definition: SQL-style definition of the table type
                               e.g. `boolean` or `varchar(256)`
    """
    curtype = column_type(cr, table, column)
    if curtype:
        # TODO compare with definition
        pass
    else:
        _params = {
            "table": sql.Identifier(table),
            "column": sql.Identifier(column),
            "definition": sql.SQL(definition),
        }
        _query = sql.SQL(
            """

            ALTER TABLE {table} ADD COLUMN {column} {definition}

        """
        ).format(**_params)
        cr.execute(_query, locals())


def remove_column(cr, table, column, cascade=False):
    """Remove a column.

        :param str table: name of the table on which the column will be dropped
        :param str column: name of the column to drop
        :param bool cascade: if True, all records having a FKEY pointing to this column
                             will be cascade-deleted (default: False)
    """
    if column_exists(cr, table, column):
        drop_depending_views(cr, table, column)
        _params = {
            "table": sql.Identifier(table),
            "column": sql.Identifier(column),
            "drop_cascade": sql.SQL("CASCADE" if cascade else ""),
        }
        _query = sql.SQL(
            """

            ALTER TABLE {table} DROP COLUMN {column} {drop_cascade}

        """
        ).format(**_params)
        cr.execute(_query, locals())


def get_columns(cr, table, ignore=("id",), extra_prefixes=None):
    """
    Get the list of column in a table, minus ignored ones.

    Can also returns the list multiple times with different prefixes.
    This can be used to duplicating records (INSERT SELECT from the same table)

        :param table: table toinspect
        :param ignore=('id'): tuple of column names to ignore
    """
    select = sql.SQL("quote_ident(column_name)")
    params = []
    if extra_prefixes:
        select = sql.SQL(",").join(
            [select]
            + [sql.SQL("concat(%s, '.', {select}").format(select)] * len(extra_prefixes)
        )
        params = list(extra_prefixes)

    _params = {"select": select}
    _query = sql.SQL(
        """

        SELECT {select}
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name NOT IN %s

    """
    ).format(**_params)
    cr.execute(_query, params + [table, ignore])  # Params is a list of unnamed args
    return list(zip(*cr.fetchall()))


def get_depending_views(cr, table, column):
    """Get the list of SQL views depending on the specified column."""
    # http://stackoverflow.com/a/11773226/75349
    _query = sql.SQL(
        """

        SELECT DISTINCT quote_ident(dependee.relname)
        FROM pg_depend
        JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
        JOIN pg_class AS dependee ON pg_rewrite.ev_class = dependee.oid
        JOIN pg_class AS dependent ON pg_depend.refobjid = dependent.oid
        JOIN pg_attribute ON pg_depend.refobjid = pg_attribute.attrelid
        AND pg_depend.refobjsubid = pg_attribute.attnum
        WHERE dependent.relname = %(table)s
          AND pg_attribute.attnum > 0
          AND pg_attribute.attname = %(column)s
          AND dependee.relkind='v'

    """
    )
    cr.execute(_query, locals())
    return map(itemgetter(0), cr.fetchall())


def drop_depending_views(cr, table, column):
    """Drop views depending on a column.

    This is usually used to ensure that modifying fields will not make
    SQL views (auto=False models) crash after the upgrade, forcing them
    to be regenerated during the uprade.
    """
    for view in get_depending_views(cr, table, column):
        _params = {"view": sql.Identifier(view)}
        _query = sql.SQL(
            """

            DROP VIEW IF EXISTS {} CASCADE

        """
        ).format(**_params)
        cr.execute(_query, locals())


def get_fk(cr, table):
    """Get the list of foreign keys pointing to `table`

        :rtype: list(tuple)
        :return: [(foreign_table, foreign_column, constraint_name, on_delete_action)]
                 where on_delete_action if one of the following:
                 - a: no action
                 - r: restrict
                 - c: cascade
                 - n: set null
                 - d: set default
    """

    _query = sql.SQL(
        """

        SELECT quote_ident(cl1.relname) AS TABLE,
               quote_ident(att1.attname) AS COLUMN,
               quote_ident(con.conname) AS conname,
               con.confdeltype
        FROM pg_constraint AS con,
             pg_class AS cl1,
             pg_class AS cl2,
             pg_attribute AS att1,
             pg_attribute AS att2
        WHERE con.conrelid = cl1.oid
          AND con.confrelid = cl2.oid
          AND array_lower(con.conkey, 1) = 1
          AND con.conkey[1] = att1.attnum
          AND att1.attrelid = cl1.oid
          AND cl2.relname = %(table)s
          AND att2.attname = 'id'
          AND array_lower(con.confkey, 1) = 1
          AND con.confkey[1] = att2.attnum
          AND att2.attrelid = cl2.oid
          AND con.contype = 'f'

    """
    )
    cr.execute(_query, locals())
    return cr.fetchall()


def delete_unused(cr, table, xmlids, set_noupdate=True):
    """
    Delete all records in the provided list not being referenced in any FKEY.

    Note that the xmlids themselves are not removed.

        :param table: target table for the deletion
        :param xmlids: list of xmlids to be checked and potentially deleted
        :param set_noupdate=True: if set, the noupdate field of all the provided
                                  xmlids will be set to True
    """
    sub = sql.SQL(" UNION ").join(
        [
            sql.SQL(
                """

                SELECT 1
                FROM "{}" x
                WHERE x."{}" = t.id

            """.format(
                    f[0], f[1]
                )
            )
            for f in get_fk(cr, table)
        ]
    )
    idmap = {ref(cr, x): x for x in xmlids}
    idmap.pop(None, None)
    if not sub or not idmap:
        return
    idmap = list(idmap)
    _params = {"table": sql.Identifier(table), "subquery": sub}
    _query = sql.SQL(
        """

        SELECT id
        FROM {table} t
        WHERE id = ANY(%(idmap)s)
          AND NOT EXISTS({subquery})

    """
    ).format(**_params)
    cr.execute(_query, locals())

    for (tid,) in cr.fetchall():
        remove_record(cr, idmap.pop(tid))

    if set_noupdate:
        for xid in idmap.values():
            force_noupdate(cr, xid, True)


def get_index_on(cr, table, *columns):
    """Get the list of indexes on the provided column names.

        :rtype: list(tuple)
        :return:a [(index_name, unique, pk)]
    """
    columns = sorted(columns)
    _query = sql.SQL(
        """


        SELECT name,
               indisunique,
               indisprimary
        FROM
          (SELECT quote_ident(i.relname) AS name,
                  x.indisunique,
                  x.indisprimary,
                  array_agg(a.attname::text
                            ORDER BY a.attname) AS attrs
           FROM
             (SELECT *,
                     unnest(indkey) AS unnest_indkey
              FROM pg_index) x
           JOIN pg_class c ON c.oid = x.indrelid
           JOIN pg_class i ON i.oid = x.indexrelid
           JOIN pg_attribute a ON (a.attrelid=c.oid
                                   AND a.attnum=x.unnest_indkey)
           WHERE (c.relkind = ANY (ARRAY['r'::"char", 'm'::"char"]))
             AND i.relkind = 'i'::"char"
             AND c.relname = %(table)s
           GROUP BY 1,
                    2,
                    3 ) idx
        WHERE attrs = %(columns)s

    """
    )
    cr.execute(_query, locals())
    return cr.fetchone()


def pg_array_uniq(a, drop_null=False):
    """???"""
    dn = "WHERE x IS NOT NULL" if drop_null else ""
    return "ARRAY(SELECT x FROM unnest({}) x {} GROUP BY x)".format(a, dn)


def pg_html_escape(s, quote=True):
    """SQL version of html.escape"""
    replacements = [("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")]  # Must be done first!
    if quote:
        replacements += [('"', "&quot;"), ("'", "&#x27;")]

    def q(s):
        return (
            psycopg2.extensions.QuotedString(s).getquoted().decode("utf-8")
        )  # noqa: E704

    return reduce(
        lambda s, r: "replace({}, {}, {})".format(s, q(r[0]), q(r[1])), replacements, s
    )


def pg_text2html(s):
    return r"CONCAT('<p>', replace({}, E'\n', '<br>'), '</p>')".format(
        pg_html_escape(s)
    )


def view_exists(cr, view):
    """Check if the specified SQL view exists."""

    _query = sql.SQL(
        """

        SELECT 1
        FROM information_schema.views
        WHERE TABLE_NAME=%(view)s

    """
    )
    cr.execute(_query, locals())
    return bool(cr.rowcount)


# ----------------- Utils -----------------


def remove_record(cr, name, deactivate=False, active_field="active"):
    """
    Remove a record from the database by xmlid.

        :param str name: fully qualified xmlid (<module>.<name>)
        :param boolean deactivate: if True, the record may be archived if
                                   deletion is impossible (eg FKEY constraint)
        :param str active_field: name of the field to use for deactivation,
                                 'active' by default
    """
    if "." not in name:
        raise ValueError("Please use fully qualified name <module>.<name>")
    module, name = name.split(".")

    _query = sql.SQL(
        """

        DELETE
        FROM ir_model_data
        WHERE module = %(module)s
          AND name = %(name)s RETURNING model, res_id

    """
    )
    cr.execute(_query, locals())
    data = cr.fetchone()
    if not data:
        return
    model, res_id = data
    table = table_of_model(cr, model)
    try:
        with savepoint(cr):
            cr.execute('DELETE FROM "%s" WHERE id=%%s' % table, (res_id,))
    except Exception:
        if not deactivate or not active_field:
            raise
        _params = {
            "table": sql.Identifier(table),
            "active_field": sql.Identifier(active_field),
        }
        _query = sql.SQL(
            """

            UPDATE {table}
            SET {active_field} = FALSE
            WHERE id = %(res_id)s

        """
        ).format(**_params)
        cr.execute(_query, locals())
    else:
        # delete all indirect references to the record (e.g. mail_message entries, etc.)
        for ir in indirect_references(cr, bound_only=True):
            _params = {
                "table": sql.Identifier(ir.table),
                "where_clause": sql.SQL(ir.model_filter(placeholder="%(model)s")),
                "res_id": sql.Identifier(ir.res_id),
            }
            _query = sql.SQL(
                """

                DELETE
                FROM {table}
                WHERE {where_clause}
                  AND {res_id} = %(res_id)s

            """
            ).format(**_params)
            cr.execute(_query, locals())


def splitlines(s):
    """Yield stripped lines of `s`.

    Skip empty lines & remove comments (starts with `#`).
    """
    return (sl for l in s.splitlines() for sl in [l.split("#", 1)[0].strip()] if sl)


def expand_braces(s):
    """Expand braces (a la bash).

    Only handle one expension of a 2 parts (because we don't need more).
    """
    r = re.compile(r"(.*){([^},]*?,[^},]*?)}(.*)")
    m = r.search(s)
    if not m:
        raise ValueError("No braces to expand")
    head, match, tail = m.groups()
    a, b = match.split(",")
    return [head + a + tail, head + b + tail]


class IndirectReference(
    namedtuple("IndirectReference", "table res_model res_id res_model_id")
):
    def model_filter(self, prefix="", placeholder="%s"):
        if prefix and prefix[-1] != ".":
            prefix += "."
        if self.res_model_id:
            placeholder = "(SELECT id FROM ir_model WHERE model={})".format(placeholder)
            column = self.res_model_id
        else:
            column = self.res_model

        return '{}"{}"={}'.format(prefix, column, placeholder)


# allow the class to handle defaults implicitely
IndirectReference.__new__.__defaults__ = (
    None,
    None,
)  # https://stackoverflow.com/a/18348004


def indirect_references(cr, bound_only=False):
    IR = IndirectReference
    each = [
        IR("ir_attachment", "res_model", "res_id"),
        IR("ir_cron", "model", None),
        IR("ir_act_report_xml", "model", None),
        IR("ir_act_window", "res_model", "res_id"),
        IR("ir_act_window", "src_model", None),
        IR("ir_act_server", "wkf_model_name", None),
        IR("ir_act_server", "crud_model_name", None),
        IR("ir_act_client", "res_model", None),
        IR("ir_model", "model", None),
        IR("ir_model_fields", "model", None),
        # destination of a relation field
        IR("ir_model_fields", "relation", None),
        IR("ir_model_data", "model", "res_id"),
        IR("ir_filters", "model_id", None),  # YUCK!, not an id
        IR("ir_exports", "resource", None),
        IR("ir_ui_view", "model", None),
        IR("ir_values", "model", "res_id"),
        IR("wkf_transition", "trigger_model", None),
        IR("wkf_triggers", "model", None),
        IR("ir_model_fields_anonymization", "model_name", None),
        IR("ir_model_fields_anonymization_migration_fix", "model_name", None),
        IR("base_import_import", "res_model", None),
        IR("calendar_event", "res_model", "res_id"),  # new in saas~18
        IR("mail_template", "model", None),
        IR("mail_activity", "res_model", "res_id", "res_model_id"),
        IR("mail_alias", None, "alias_force_thread_id", "alias_model_id"),
        IR("mail_alias", None, "alias_parent_thread_id", "alias_parent_model_id"),
        IR("mail_followers", "res_model", "res_id"),
        IR("mail_message_subtype", "res_model", None),
        IR("mail_message", "model", "res_id"),
        IR("mail_compose_message", "model", "res_id"),
        IR("mail_wizard_invite", "res_model", "res_id"),
        IR("mail_mail_statistics", "model", "res_id"),
        IR("mail_mass_mailing", "mailing_model", None),
        IR("project_project", "alias_model", None),
        IR("rating_rating", "res_model", "res_id", "res_model_id"),
        IR("rating_rating", "parent_res_model", "parent_res_id", "parent_res_model_id"),
    ]

    for ir in each:
        if bound_only and not ir.res_id:
            continue
        if ir.res_id and not column_exists(cr, ir.table, ir.res_id):
            continue

        # some `res_model/res_model_id` combination may change between
        # versions (i.e. rating_rating.res_model_id was added in saas~15).
        # we need to verify existance of columns before using them.
        if ir.res_model and not column_exists(cr, ir.table, ir.res_model):
            ir = ir._replace(res_model=None)
        if ir.res_model_id and not column_exists(cr, ir.table, ir.res_model_id):
            ir = ir._replace(res_model_id=None)
        if not ir.res_model and not ir.res_model_id:
            continue

        yield ir


def res_model_res_id(cr):
    """Iterate on base models having a field that references records by model/id.

    Allow iterating on all models that reference records by using a
    res_model/res_id field combiination of similar reference system;
    usually used to quickly iterate over basic ORM models (views, crons, etc.)
    that references other models in an indirect way (without FKEY).

        :rtype tuple:
        :return: tuple containing the model, model reference field name
                 and id reference field name
    """
    for ir in indirect_references(cr):
        if ir.res_model:
            yield model_of_table(cr, ir.table), ir.res_model, ir.res_id


@contextmanager
def skippable_cm():
    """Allow a contextmanager to not yield."""
    if not hasattr(skippable_cm, "_msg"):

        @contextmanager
        def _():
            if 0:
                yield

        try:
            with _():
                pass
        except RuntimeError as r:
            skippable_cm._msg = str(r)
    try:
        yield
    except RuntimeError as r:
        if str(r) != skippable_cm._msg:
            raise


@contextmanager
def savepoint(cr):
    """Provide a savepoint context.

    If a query executed in this context fails, the operation is rollbacked,
    otherwise it success silently.
    """
    name = hex(int(time.time() * 1000))[1:]
    cr.execute("SAVEPOINT {}".format(name))
    try:
        yield
        cr.execute("RELEASE SAVEPOINT {}".format(name))
    except Exception:
        cr.execute("ROLLBACK TO SAVEPOINT {}".format(name))
        raise


def log_progress(it, qualifier="elements", logger=_logger, size=None):
    if size is None:
        size = len(it)
    size = float(size)
    t0 = t1 = datetime.datetime.now()
    for i, e in enumerate(it, 1):
        yield e
        t2 = datetime.datetime.now()
        if (t2 - t1).total_seconds() > 60:
            t1 = datetime.datetime.now()
            tdiff = t2 - t0
            logger.info(
                "[%.02f%%] %d/%d %s processed in %s (TOTAL estimated time: %s)",
                (i / size * 100.0),
                i,
                size,
                qualifier,
                tdiff,
                datetime.timedelta(seconds=tdiff.total_seconds() * size / i),
            )


def env(cr):
    """Get an environment for the SUPERUSER ('admin')."""
    from odoo.api import Environment

    return Environment(cr, SUPERUSER_ID, {})


def import_script(path):
    """Import a script from another module.

    This can be used if some changes have been applied across the whole
    codebase but would need module-specific changes; e.g. a generic script
    can be defined in the `base` module and called by any relevant module
    who might want to use it to adapt something depending on values depending
    from that module.

        :param path: relative path to the script
                     <module>/<versions>/<script>
                     e.g. base/12.0.1.3/do_stuff.py
    """
    name, _ = os.path.splitext(os.path.basename(path))
    full_path = os.path.join(os.path.dirname(__file__), path)
    with open(full_path) as fp:
        return imp.load_source(name, full_path, fp)


def dispatch_by_dbuuid(cr, version, callbacks):
    """Apply dbuuid-specific migrations.

    Allow defining custom migration functions that can be applied on a
    single database identified by its uuid, e.g.:

    _db_callback(cr, version):
        # do stuff specific to that db

    def migrate(cr, version):
        migration.dispatch_by_dbuuid(cr, version, {
            '88ef269b-f6de-4f76-b9c8-868fc5569136': _db_callback,
        })

    The callback function _db_callback should have the same signature as a
    `migrate` function, taking the cursor `cr` and `version` as args.

        :param version: target version for this upgrade
        :param callbacks: dict where each key is a uuid and value is a
                          reference to the callback function
    """
    uuid = dbuuid(cr)
    if uuid in callbacks:
        func = callbacks[uuid]
        _logger.info("calling dbuuid-specific function `%s`", func.__name__)
        func(cr, version)


def register_unanonymization_query(
    cr, model, field, query, query_type="sql", sequence=10
):
    """
    Generate an unanonymization query.

    Allow newly created fields, values, etc. to be deanonymzed even though they
    were not present during anonymization (e.g. when values are moved/copied).

        :param model:
        :param field:
        :param query:
        :param query_type='sql':
        :param sequence=10:
    """
    target_version = release.major_version
    _query = sql.SQL(
        """
        INSERT INTO ir_model_fields_anonymization_migration_fix( target_version, sequence, query_type, model_name, field_name, query )
        VALUES (%(target_version)s,
                %(sequence)s,
                %(query_type)s,
                %(model)s,
                %(field)s,
                %(query)s)

    """
    )
    cr.execute(_query, locals())


def _rst2html(rst):
    """Convert rst to html."""
    overrides = dict(
        embed_stylesheet=False,
        doctitle_xform=False,
        output_encoding="unicode",
        xml_declaration=False,
    )
    html = publish_string(
        source=dedent(rst), settings_overrides=overrides, writer=MyWriter()
    )
    return html_sanitize(html, silent=False)


def _md2html(md):
    """Convert markdown to html."""
    extensions = [
        "markdown.extensions.smart_strong",
        "markdown.extensions.nl2br",
        "markdown.extensions.sane_lists",
    ]
    return markdown.markdown(md, extensions=extensions)


# ---------- xmlid utilities ----------


def ref(cr, xmlid):
    """Get the id of an xmlid entry."""
    if "." not in xmlid:
        raise ValueError("Please use fully qualified name <module>.<name>")

    module, name = xmlid.split(".")

    _query = sql.SQL(
        """

        SELECT res_id
        FROM ir_model_data
        WHERE module = %(module)s
          AND name = %(name)s

    """
    )
    cr.execute(_query, locals())
    data = cr.fetchone()
    if data:
        return data[0]
    return None


def rename_xmlid(cr, old, new, noupdate=None):
    """Rename an xmlid.

    In the case of a view xmlid, the key if the view is updated as well.
    """
    if "." not in old or "." not in new:
        raise ValueError("Please use fully qualified name <module>.<name>")

    old_module, old_name = old.split(".")
    new_module, new_name = new.split(".")
    noupdate = sql.SQL(
        "" if noupdate is None else (", noupdate=" + str(bool(noupdate)).lower())
    )
    _params = {"noupdate": noupdate}
    _query = sql.SQL(
        """

        UPDATE ir_model_data
        SET module = %(new_module)s,
            name=%(new_name)s {noupdate}
        WHERE module = %(old_module)s
          AND name = %(old_name)s RETURNING model,
                      res_id

    """
    ).format(**_params)
    cr.execute(_query, locals())
    data = cr.fetchone()
    if data:
        model, rid = data
        if model == "ir.ui.view":
            _update_view_key(cr, old, new)
            _query = sql.SQL(
                """

                UPDATE ir_ui_view
                SET key = %(new)s
                WHERE id = %(rid)s
                  AND key = %(old)s

            """
            ).format(**_params)
            cr.execute(_query, locals())
        return rid
    return None


def force_noupdate(cr, xmlid, noupdate=True, warn=False):
    """Force the noupdate value of an xmlid."""
    if "." not in xmlid:
        raise ValueError("Please use fully qualified name <module>.<name>")

    module, name = xmlid.split(".")
    _query = sql.SQL(
        """

        UPDATE ir_model_data
        SET noupdate = %(noupdate)s
        WHERE module = %(module)s
          AND name = %(name)s
          AND noupdate != %(noupdate)s

    """
    )
    cr.execute(_query, locals())
    if noupdate is False and cr.rowcount and warn:
        _logger.warning("Customizations on `%s` might be lost!", xmlid)
    return cr.rowcount


def ensure_xmlid_match_record(cr, xmlid, model, values):
    """Ensure the provided values matches the provided xmlid.

    Check the provided model table for the presence of a record matching
    the given xmlid. If the record is not found, searches the table for
    any record matching the provided values and associate it to the xmlid.

        :param str xmlid: fully qualified xmlid (<module>.<name>)
        :param str model: name of the model to check (Odoo model name)
        :param tuple values: column name and value to check if the record needs
                             to be found in the table (will be used in a WHERE
                             query)
        :rtype: integer
        :return: ID of the record
    """
    if "." not in xmlid:
        raise ValueError("Please use fully qualified name <module>.<name>")

    module, name = xmlid.split(".")
    _query = sql.SQL(
        """

        SELECT id,
               res_id
        FROM ir_model_data
        WHERE module = %(module)s
          AND name = %(name)s

    """
    )
    cr.execute(_query, locals())

    table = table_of_model(cr, model)
    data = cr.fetchone()
    if data:
        data_id, res_id = data
        # check that record still exists
        _params = {"table": sql.Identifier(table)}
        _query = sql.SQL(
            """
            SELECT id
            FROM {table}
            WHERE id = %(res_id)s

        """
        ).format(**_params)
        cr.execute(_query, locals())
        if cr.fetchone():
            return res_id
    else:
        data_id = None

    # search for existing record marching values
    where = sql.Composed([])
    data = ()
    for field, value in values.items():
        _params = {"field": sql.Identifier(field)}
        if value:
            _params["value"] = sql.Literal(value)
            where += sql.Composed([sql.SQL("{field} = {value}").format(**_params)])
            data += (value,)
        else:
            where += sql.Composed([sql.SQL("{field} IS NULL").format(**_params)])
            data += ()

    _params = {"table": sql.Identifier(table), "where": where.join(" AND ")}
    _query = sql.SQL(
        """
        SELECT id
        FROM {table}
        WHERE {where}

    """
    ).format(**_params)
    cr.execute(_query, locals())
    record = cr.fetchone()
    if not record:
        return None

    res_id = record[0]

    # update xmlid table
    if data_id:
        _query = sql.SQL(
            """

            UPDATE ir_model_data
            SET res_id = %(res_id)s
            WHERE id = %(data_id)s

        """
        )
        cr.execute(_query, locals())
    else:

        _query = sql.SQL(
            """

            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES (%(module)s,
                    %(name)s,
                    %(model)s,
                    %(res_id)s,
                    TRUE)

        """
        )
        cr.execute(_query, locals())
    return res_id


# -------- Announcement Message --------


_DEFAULT_HEADER = """
<p>{module} has been upgraded to version {version}.</p>
<h2>What's new in this upgrade?</h2>
"""

_DEFAULT_FOOTER = "<p>Enjoy this new version of {module}!</p>"

_DEFAULT_RECIPIENT = "mail.channel_all_employees"


def announce(
    cr,
    module,
    version,
    msg,
    format="rst",
    recipient=_DEFAULT_RECIPIENT,
    header=_DEFAULT_HEADER,
    footer=_DEFAULT_FOOTER,
    pluses_for_enterprise=None,
):
    """
    Post an upgrade message in the selected channel detailing the upgrade.

        :param module: nmae of the upgraded module
        :param version: target upgrade version
        :param msg: message regarding the upgrade
        :param format='rst': format of the message
                             ('rst' for ReStructured Text or 'md' for markdown)
        :param recipient: xmlid of the channel where the message will be posted
        :param header: header of the message (set False for no header)
        :param footer: footer of the message (set False for no footer)
        :param pluses_for_enterprise=None: if True, list elements in your message
                                           prefixed with a '+ ' string will be
                                           filtered out if the upgraded database
                                           does not have the Enterprise edition
    """
    if pluses_for_enterprise:
        plus_re = r"^(\s*)\+ (.+)\n"
        replacement = r"\1- \2\n" if has_enterprise() else ""
        msg = re.sub(plus_re, replacement, msg, flags=re.M)

    # do not notify early, in case the migration fails halfway through
    ctx = {"mail_notify_force_send": False, "mail_notify_author": True}

    try:
        registry = env(cr)
        user = registry["res.users"].browse([SUPERUSER_ID])[0].with_context(ctx)

        def ref(xid):
            return registry.ref(xid).with_context(ctx)

    except MigrationError:
        registry = Registry.get(cr.dbname)
        user = registry["res.users"].browse(cr, SUPERUSER_ID, SUPERUSER_ID, context=ctx)

        def ref(xid):
            rmod, _, rxid = recipient.partition(".")
            return registry["ir.model.data"].get_object(
                cr, SUPERUSER_ID, rmod, rxid, context=ctx
            )

    # default recipient
    poster = user.message_post

    if recipient:
        try:
            poster = ref(recipient).message_post
        except (ValueError, AttributeError):
            # Cannot find record, post the message on the wall of the admin
            pass

    if format == "rst":
        msg = _rst2html(msg)
    elif format == "md":
        msg = _md2html(msg)

    message = ((header or "") + msg + (footer or "")).format(
        module=module or "Odoo", version=version
    )
    _logger.debug(message)

    type_field = "message_type"
    kw = {type_field: "notification"}

    try:
        poster(
            body=message,
            partner_ids=[user.partner_id.id],
            subtype="mail.mt_comment",
            **kw
        )
    except Exception:
        _logger.warning("Cannot announce message", exc_info=True)


# --- NOT SURE IF STILL NEEDED ??? --- #


def main(func, version=None):
    """a main() function for scripts"""
    # NOTE: this is not recommanded when the func callback use the ORM as the addon-path is
    # incomplete. Please pipe your script into `odoo shell`.
    # Do not forget to commit the cursor at the end.
    if len(sys.argv) != 2:
        sys.exit("Usage: {} <dbname>".format(sys.argv[0]))
    dbname = sys.argv[1]
    with db_connect(dbname).cursor() as cr, Environment.manage():
        func(cr, version)


def _ir_values_value(cr):
    # returns the casting from bytea to text needed in saas~17 for column `value` of `ir_values`
    # returns tuple(column_read, cast_write)
    result = getattr(_ir_values_value, "result", None)

    if result is None:
        if column_type(cr, "ir_values", "value") == "bytea":
            cr.execute(
                "SELECT character_set_name FROM information_schema.character_sets"
            )
            charset, = cr.fetchone()
            column_read = "convert_from(value, '%s')" % charset
            cast_write = "convert_to(%%s, '%s')" % charset
        else:
            column_read = "value"
            cast_write = "%s"
        _ir_values_value.result = result = (column_read, cast_write)

    return result


def chunks(iterable, size, fmt=None):
    """
    Split `iterable` into chunks of `size` and wrap each chunk
    using function 'fmt' (`iter` by default; join strings)

    >>> list(chunks(range(10), 4, fmt=tuple))
    [(0, 1, 2, 3), (4, 5, 6, 7), (8, 9)]
    >>> ' '.join(chunks('abcdefghijklm', 3))
    'abc def ghi jkl m'
    >>>

    """
    if fmt is None:
        fmt = "".join

    it = iter(iterable)
    try:
        while True:
            yield fmt(chain((next(it),), islice(it, size - 1)))
    except StopIteration:
        return


def iter_browse(model, *args, **kw):
    """
    Iterate and browse through record without filling the cache.
    `args` can be `cr, uid, ids` or just `ids` depending on kind of `model` (old/new api)
    """
    assert len(args) in [1, 3]  # either (cr, uid, ids) or (ids,)
    cr_uid = args[:-1]
    ids = args[-1]
    chunk_size = kw.pop("chunk_size", 200)  # keyword-only argument
    logger = kw.pop("logger", _logger)
    if kw:
        raise TypeError("Unknow arguments: %s" % ", ".join(kw))

    def browse(ids):
        model.invalidate_cache(*cr_uid)
        args = cr_uid + (list(ids),)
        return model.browse(*args)

    def end():
        model.invalidate_cache(*cr_uid)
        if 0:
            yield

    it = chain.from_iterable(chunks(ids, chunk_size, fmt=browse))
    if logger:
        it = log_progress(it, qualifier=model._name, logger=logger, size=len(ids))

    return chain(it, end())
