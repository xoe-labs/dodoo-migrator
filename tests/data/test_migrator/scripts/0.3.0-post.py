from odoo import migration

migration.create_column(cr, "res_partner", "post_script_column", "VARCHAR")  # noqa
