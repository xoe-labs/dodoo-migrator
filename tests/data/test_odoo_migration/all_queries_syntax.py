import sys

from odoo import migration

migration.module_installed(cr, "base")  # noqa
# ALSO TOUCHES: modules_installed
migration.remove_module(cr, "iap")  # noqa
# ALSO TOUCHES: table_of_model
# ALSO TOUCHES: table_exists
# ALSO TOUCHES: remove_view
# ALSO TOUCHES: remove_record
# ALSO TOUCHES: remove_menus
# ALSO TOUCHES: remove_model
# ALSO TOUCHES: indirect_references
# ALSO TOUCHES: column_exists
# ALSO TOUCHES: column_type
# ALSO TOUCHES: table_exists
# ALSO TOUCHES: view_exists
# ALSO TOUCHES: remove_field
# ALSO TOUCHES: remove_refs
migration.rename_module(cr, "web_tour", "web_tours")  # noqa
migration.merge_module(cr, "web_tours", "web")  # noqa
migration.force_install_module(cr, "sale", deps=["mrp"])  # noqa
migration.force_install_module(cr, "sale", deps=None)  # noqa
migration.module_deps_diff(cr, "sale", ("stock",), ("stock",))  # noqa
# ALSO TOUCHES: new_module_dep
# ALSO TOUCHES: force_install_module
# ALSO TOUCHES: remove_module_deps

# TODO: Needs special preparation
# migration.new_module(cr,  module, deps=(), auto_install=False)  # noqa
# ALSO TOUCHES: new_module_dep
# ALSO TOUCHES: modules_installed

# NOTE: Cannot be readily tested as it analyzes the executin environment
# and infers a version from the file
# migration.force_migration_of_fresh_module(cr, "sale")  # noqa
migration.split_group(cr, "base.group_user", "base.group_system")  # noqa

migration.create_m2m(
    cr, "rel_tbl", "res_partner", "res_company", col1=None, col2=None
)  # noqa
migration.create_m2m(
    cr, "rel_tbl2", "res_partner", "res_company", col1="col1", col2="col2"
)  # noqa
migration.ensure_m2o_func_field_data(
    cr, "res_partner", "user_id", "res_company"
)  # noqa
# ALSO TOUCHES: column_exists
# ALSO TOUCHES: remove_column

# TODO: https://github.com/odoo/odoo/pull/26548#pullrequestreview-234117381
# migration.uniq_tags(cr, "res.partner.category", uniq_column="name", order="id")  # noqa
# ALSO TOUCHES: table_of_model
# ALSO TOUCHES: get_columns


migration.move_field_to_module(cr, "res.partner", "color", "base", "web")  # noqa
migration.rename_field(
    cr, "res.partner", "name", "name2", update_references=True
)  # noqa
# ALSO TOUCHES: table_of_model
# ALSO TOUCHES: table_exists
# ALSO TOUCHES: column_exists
# ALSO TOUCHES: update_field_references
migration.make_field_company_dependent(
    cr, "res.partner", "title", "many2one", target_model="res.partner.title"
)  # noqa
# ALSO TOUCHES: remove_column
# ALSO TOUCHES: drop_depending_views
# ALSO TOUCHES: get_depending_views

# TODO: We most probably destroyed the schema by now
# migration.recompute_fields(cr, model, fields, ids=None, logger=_logger, chunk_size=256)  # noqa

# TODO: check what it does
# migration.fix_wrong_m2o(cr, table, column, target, value=None)


migration.move_model(
    cr, "res.lang", "base", "web", move_data=True, delete=False
)  # noqa
migration.rename_model(
    cr, "res.currency.rate", "res.currency.rates", rename_table=True
)  # noqa
# ALSO TOUCHES: res_model_res_id

migration.replace_record_references(
    cr, ("res.partner", 2), (None, 1), replace_xmlid=True
)  # noqa
# ALSO TOUCHES: replace_record_references_batch
# ALSO TOUCHES: get_fk

migration.create_column(cr, "res_partner", "new_col", "varchar")  # noqa

# TODO: construe a test case
# migration.delete_unused(cr, table, xmlids, set_noupdate=True)  # noqa
# ALSO TOUCHES: force_noupdate

migration.get_index_on(cr, "res_currency", ["name"])  # noqa

migration.rename_xmlid(
    cr, "base.main_company", "base.main_company2", noupdate=None
)  # noqa
# Found
migration.ensure_xmlid_match_record(
    cr, "base.main_company2", "res.company", {"name": "My Company"}
)  # noqa
# Not Found (any more)
migration.ensure_xmlid_match_record(
    cr, "base.main_company", "res.company", {"name": "My Company"}
)  # noqa

cr.commit()

# We destroyed the database, prevent loading registry (which would fail)
sys.exit()
