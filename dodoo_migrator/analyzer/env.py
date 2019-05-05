# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from contextlib import contextmanager

import odoo
from odoo.api import Environment


@contextmanager
def OdooAnalyzerEnvironment(database):
    with Environment.manage():
        registry = odoo.registry(database)
        try:
            with registry.cursor() as cr:
                uid = odoo.SUPERUSER_ID
                ctx = Environment(cr, uid, {})["res.users"].context_get()
                env = Environment(cr, uid, ctx)
                cr.rollback()
                yield env
                cr.rollback()
        finally:
            odoo.modules.registry.Registry.delete(database)
            odoo.sql_db.close_db(database)
