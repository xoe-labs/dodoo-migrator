# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


SELECTION_GROUP_HIERARCHY = {"4": ["3", "2", "1"], "3": ["2", "1"], "2": ["1"], "1": []}


# fmt: off
KNOWN_FIELD_NON_SLOT_ATTRIBUTES = {
    'type'                : {'selection_group': '4'},        # type of the field (string)
    'relational'          : {'selection_group': '4'},        # whether the field is a relational one
    'translate'           : {'selection_group': '4'},        # whether the field is translated
}

KNOWN_FIELD_SLOTS = {

    # fields.MetaField
    'args'                : {'selection_group': '4'},       # the parameters given to __init__()
    '_attrs'              : {'selection_group': '4'},       # the field's non-slot attributes
    '_module'             : {'selection_group': '4'},       # the field's module name
    '_modules'            : {'selection_group': '4'},       # modules that define this field
    '_setup_done'         : {'selection_group': '4'},       # the field's setup state : None, 'base' or 'full'
    '_sequence'           : {'selection_group': '4'},       # absolute ordering of the field

    'automatic'           : {'selection_group': '4'},       # whether the field is automatically created ("magic" field)
    'inherited'           : {'selection_group': '4'},       # whether the field is inherited (_inherits)
    'inherited_field'     : {'selection_group': '4'},       # the corresponding inherited field

    'name'                : {'selection_group': '4'},       # name of the field
    'model_name'          : {'selection_group': '4'},       # name of the model of this field
    'comodel_name'        : {'selection_group': '4'},       # name of the model of values (if relational)

    'store'               : {'selection_group': '4'},       # whether the field is stored in database
    'index'               : {'selection_group': '4'},       # whether the field is indexed in database
    'manual'              : {'selection_group': '4'},       # whether the field is a custom field
    'copy'                : {'selection_group': '4'},       # whether the field is copied over by BaseModel.copy()
    'depends'             : {'selection_group': '4'},       # collection of field dependencies
    'recursive'           : {'selection_group': '4'},       # whether self depends on itself
    'compute'             : {'selection_group': '4'},       # compute(recs) computes field on recs
    'compute_sudo'        : {'selection_group': '4'},       # whether field should be recomputed as admin
    'inverse'             : {'selection_group': '4'},       # inverse(recs) inverses field on recs
    'search'              : {'selection_group': '4'},       # search(recs, operator, value) searches on self
    'related'             : {'selection_group': '4'},       # sequence of field names, for related fields
    'related_sudo'        : {'selection_group': '4'},       # whether related fields should be read as admin
    'company_dependent'   : {'selection_group': '4'},       # whether ``self`` is company-dependent (property field)
    'default'             : {'selection_group': '4'},       # default(recs) returns the default value

    'string'              : {'selection_group': '4'},       # field label
    'help'                : {'selection_group': '4'},       # field tooltip
    'readonly'            : {'selection_group': '4'},       # whether the field is readonly
    'required'            : {'selection_group': '4'},       # whether the field is required
    'states'              : {'selection_group': '4'},       # set readonly and required depending on state
    'groups'              : {'selection_group': '4'},       # csv list of group xml ids
    'change_default'      : {'selection_group': '4'},       # whether the field may trigger a "user-onchange"
    'deprecated'          : {'selection_group': '4'},       # whether the field is deprecated

    'related_field'       : {'selection_group': '4'},       # corresponding related field
    'group_operator'      : {'selection_group': '4'},       # operator for aggregating values
    'group_expand'        : {'selection_group': '4'},       # name of method to expand groups in read_group()
    'prefetch'            : {'selection_group': '4'},       # whether the field is prefetched
    'context_dependent'   : {'selection_group': '4'},       # whether the field's value depends on context

    # fields.Char
    'size'                : {'selection_group': '4'},       # maximum size of values (deprecated)
    'trim'                : {'selection_group': '4'},       # whether value is trimmed (only by web client)

    # fields.Float
    #  `_digits` slot is accessed through `digits` property function
    'digits'              : {'selection_group': '4'},        # digits argument passed to class initializer

    # fields.Monetary
    'currency_field'      : {'selection_group': '4'},

    # fields._String
    'translate'           : {'selection_group': '4'},       # whether the field is translated

    # fields.Html
    'sanitize'            : {'selection_group': '4'},       # whether value must be sanitized
    'sanitize_tags'       : {'selection_group': '4'},       # whether to sanitize tags (only a white list of attributes is accepted)
    'sanitize_attributes' : {'selection_group': '4'},       # whether to sanitize attributes (only a white list of attributes is accepted)
    'sanitize_style'      : {'selection_group': '4'},       # whether to sanitize style attributes
    'strip_style'         : {'selection_group': '4'},       # whether to strip style attributes (removed and therefore not sanitized)
    'strip_classes'       : {'selection_group': '4'},       # whether to strip classes attributes

    # fields.Binary
    'attachment'          : {'selection_group': '4'},       # whether value is stored in attachment

    # fields.Selection
    'selection'           : {'selection_group': '4'},       # [(value, string), ...], function or method name
    'validate'            : {'selection_group': '4'},       # whether validating upon write

    # fields._Relational
    'domain'              : {'selection_group': '4'},       # domain for searching values
    'context'             : {'selection_group': '4'},       # context for searching values
    'auto_join'           : {'selection_group': '4'},       # whether joins are generated upon search

    # fields.Many2one
    'ondelete'            : {'selection_group': '4'},       # what to do when value is deleted
    'delegate'            : {'selection_group': '4'},       # whether self implements delegation

    # fields._RelationalMulti
    'limit'               : {'selection_group': '4'},       # optional limit to use upon read

    # fields.Many2many
    'relation'            : {'selection_group': '4'},       # name of table
    'column1'             : {'selection_group': '4'},       # column of table referring to model
    'column2'             : {'selection_group': '4'},       # column of table referring to comodel

    # fields.One2many
    'inverse_name'        : {'selection_group': '4'},       # name of the inverse field
}
# fmt: on
