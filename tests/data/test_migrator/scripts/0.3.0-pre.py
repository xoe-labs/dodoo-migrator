from odoo import migration

migration.create_column(cr, "res_partner", "pre_script_column", "VARCHAR")  # noqa
