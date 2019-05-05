# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


EXOGENOUS_INFORMATION_SUGGESTION = (
    "If it's identifiable as part of a cross module relocation, modify the known changes file. "
    "Meaning: It has neither a processable oldname instruction, nor is it a relocatino alongside "
    "the inheritence MRO, which are matched automatically."
)
TABLE_RENAME_DEFINITION = 'A relocation of all non-automatic columns of a table is also known as a "table rename".'
TRANSITIONS_LEVELS = {
    "0": "Nothing to do.",
    "1": "Automateable transition.",
    "2": "Exogenous transition.",
}


# fmt: off
KNOWN_SCHEMA_ATOMIC_TRANSITIONS_DESCRIPTIONS = {
    'gained_existence'                      : {'description': "Column will appear in module: {module}."},  # {module} first definition as per MRO, apply oldname + EXOGENOUS_INFORMATION preflight check
    'lost_existence'                        : {'description': "Column will disappear in module: {module}."},  # {module} first definition as per MRO, apply oldname + EXOGENOUS_INFORMATION preflight check
    'gained__modules'                       : {'description': "Column will newly be defined in: {_modules}"},
    'lost__modules'                         : {'description': "Column won't be defined any more in: {_modules}"},

    'gained_required'                       : {'description': "Column will become non nullable."},
    'lost_required'                         : {'description': "Column will become nullable."},
    'gained_type'                           : {'description': "Column will be of type {type}."},
    'lost_type'                             : {'description': "Column won't be of type {type} any more."},

    # Same type transitions (type transition shadow attriute transitions)

    # Mutually exlusive store transitions and it's variants ordered from complex to trivial
    'gained_compute'                        : {'description': "Column will be computed."},
    'lost_cmopute_stored'                   : {'description': "Column won't be computed any more, but was stored."},
    'lost_cmopute_not_stored'               : {'description': "Column won't be computed any more and wasn't stored."},
    'gained_related'                        : {'description': "Column will be related to {related}."},
    'lost_related_stored'                   : {'description': "Column won't be related to {related} any more, but was stored."},
    'lost_related_not_stored'               : {'description': "Column won't be related to {related} any more and wasn't stored."},
    'gained_company_dependent'              : {'description': "Column will be company dependent."},
    'lost_company_dependent'                : {'description': "Column won't be company dependent any more."},  # Note: company_dependent are never stored
    'gained_store'                          : {'description': "Column will be persisted in database."},
    'lost_store'                            : {'description': "Column won't be persisted in database any more."},

    'gained_deprecated'                     : {'description': "Column will be deprecated."},
    'lost_deprecated'                       : {'description': "Column won't be deprecated any more."},  # probably never gonna happen
    'gained_size'                           : {'description': "Column will be of size {size}."},
    'lost_size'                             : {'description': "Column won't be of size {size} any more."},
    'gained_attachment'                     : {'description': "Column will be stored as attachment."},
    'lost_attachment'                       : {'description': "Column won't be stored as attachment any more."},
    'gained_selection'                      : {'description': "Column will have selection {selection}."},
    'lost_selection'                        : {'description': "Column won't have selection {selection} any more."},
}


KNOWN_SCHEMA_AGGREGATE_TRANSITIONS_DESCRIPTIONS = {
    'moved_oldname'                         : {'description': "Column will be moved / renamed / relocated according to `oldname` field."},
    'moved_mro_parallel'                    : {'description': "Column will be moved / renamed / relocated along the inheritence MRO."},
    'moved_exogenous'                       : {'description': "Column will be moved / renamed / relocated according to exogenous information."},
    # Casted type transitions
    'casted'                                : {'description': "Column will be automatically type casted by the system."},

    # None-Casted Type transitions
    'from_selection_to_many2one'            : {'description': "Column will change from `selection` to `many2one`."},
    'from_many2one_to_selection'            : {'description': "Column will change from `many2one` to `selection`."},
    'from_selection_to_boolean'             : {'description': "Column will change from `selection` to `boolean`."},
    'from_boolean_to_selection'             : {'description': "Column will change from `boolean` to `selection`."},
    'from_selection_to_char'                : {'description': "Column will change from `selection` to `char`."},
    'from_char_to_selection_casted'         : {'description': "Column will change from `char` to `selection` (casted)."},
    'from_char_to_selection_not_casted'     : {'description': "Column will change from `char` to `selection` (not casted)."},
    'from_char_to_selection_invalid'        : {'description': "Column will change from `char` to `selection` (casted & invalid)."},
    'from_selection_to_integer'             : {'description': "Column will change from `selection` to `integer`."},
    'from_integer_to_selection_casted'      : {'description': "Column will change from `integer` to `selection` (casted)."},
    'from_integer_to_selection_not_casted'  : {'description': "Column will change from `integer` to `selection` (not casted)."},
    'from_integer_to_selection_invalid'     : {'description': "Column will change from `integer` to `selection` (casted & invalid)."},

    'from_many2many_to_many2one'            : {'description': "Column will change from `many2many` to `many2one`."},
    'from_many2one_to_many2many'            : {'description': "Column will change from `many2one` to `many2many`."},

    'from_float_to_integer'                 : {'description': "Column will change from `float` to `integer`."},
    'from_monetary_to_integer'              : {'description': "Column will change from `monetary` to `integer`."},  # Really?
    'from_binary_to_text_or_char_or_html'   : {'description': "Column will change from `binary` to `text` or `char` or `html`."},
    'from_text_or_char_or_html_to_binary'   : {'description': "Column will change from `text` or `char` or `html` to `binary`."},

    'not_known_not_casted'                  : {'description': "Column transition not known."},

    # Same type transitions
    'char_shrinks'                          : {'description': "Column (char type) will shrink in size."},
    'char_grows'                            : {'description': "Column (char type) will grow in size."},
    'selection_shrinks'                     : {'description': "Column (selection type) will have less options, missing options: {options}."},
    'selection_grows'                       : {'description': "Column (selection type) will have more options, additional options: {options}."},
}

# migration_semantic only defines `pre` or `post` (no `end`)
# pre are meant to be casted to the earliest possible module
# post are meant to be casted to the latest possible module
# Hence `end` semantic is a disguised `post` semantic

KNOWN_SCHEMA_ATOMIC_TRANSITIONS_INSTRUCTIONS = {
    'gained_existence'                      : {'instruction': "Pre migration can seed column values. " + EXOGENOUS_INFORMATION_SUGGESTION,                          "migration_semantic": 'pre', 'level': 2},
    'lost_existence'                        : {'instruction': "Nothing to do. It will be gone. " + EXOGENOUS_INFORMATION_SUGGESTION,                                "migration_semantic": None,  'level': 0},
    'gained__modules'                       : {'instruction': "Informational, together with module dependencies, for proper migration script (stub) casting.",      "migration_semantic": None,  'level': 2},  # Always report
    'lost__modules'                         : {'instruction': "Informational, together with module dependencies, for proper migration script (stub) casting.",      "migration_semantic": None,  'level': 2},  # Always report

    'gained_required'                       : {'instruction': "Pre migration needs to manually induce correct semantics for NULL values in that column.",           "migration_semantic": 'pre', 'level': 2},
    'lost_required'                         : {'instruction': "Nothing to do.",                                                                                     "migration_semantic": None,  'level': 0},
    'gained_type'                           : {'instruction': "Nothing to do. It's part of an aggregate transition.",                                               "migration_semantic": None,  'level': 0},
    'lost_type'                             : {'instruction': "Nothing to do. It's part of an aggregate transition.",                                               "migration_semantic": None,  'level': 0},

    # Same type transitions (type transition shadow attriute transitions)

    # Mutually exlusive store transitions and it's variants ordered from complex to trivial
    'gained_compute'                        : {'instruction': "Pre migration will need to shift (+merge) data to the sources used by the new compute function.",    "migration_semantic": 'pre', 'level': 2},
    'lost_compute_stored'                   : {'instruction': "Nothing to do.",                                                                                     "migration_semantic": None,  'level': 0},
    'lost_compute_not_stored'               : {'instruction': "Pre migration will need to force storage and trigger a recompute on old codebase.",                  "migration_semantic": 'pre', 'level': 1},
    'gained_related'                        : {'instruction': "Pre migration might need to shift (+merge) data to related target.",                                 "migration_semantic": 'pre', 'level': 1},
    'lost_related_stored'                   : {'instruction': "Nothing to do.",                                                                                     "migration_semantic": None,  'level': 0},
    'lost_related_not_stored'               : {'instruction': "Pre migration will need to force storage and trigger a recompute on old codebase.",                  "migration_semantic": 'pre', 'level': 1},
    'gained_company_dependent'              : {'instruction': "Pre migration will need to shift data to ir_property table once for every company.",                 "migration_semantic": 'pre', 'level': 1},
    'lost_company_dependent'                : {'instruction': "Pre migration will need to homologate diverging companies' values and set the chosen value.",        "migration_semantic": 'pre', 'level': lambda env: 1 if len(env['res.compay'].search() == 1) else 2},  # TODO: In reality it should target cardinality of property values
    'gained_store'                          : {'instruction': "Nothing to do. It's most probably already a computed type field.",                                   "migration_semantic": None,  'level': 0},  # Note: Never seen a non computed type with store=false
    'lost_store'                            : {'instruction': "Nothing to do. If so data will be shifted by a more specific transition",                            "migration_semantic": None,  'level': 0},

    'gained_deprecated'                     : {'instruction': "Pre migration might want to get away from this field.",                                              "migration_semantic": 'pre', 'level': 2},
    'lost_deprecated'                       : {'instruction': "Maybe it's a joke, or 1st of april. If you see this message, then open an issue somwhere.",          "migration_semantic": None,  'level': 0},
    'gained_size'                           : {'instruction': "Nothing to do. It's part of an aggregate transition.",                                               "migration_semantic": None,  'level': 0},
    'lost_size'                             : {'instruction': "Nothing to do. It's part of an aggregate transition.",                                               "migration_semantic": None,  'level': 0},
    'gained_attachment'                     : {'instruction': "Pre migration needs to transfer byte data from the column to the attachment table.",                 "migration_semantic": 'pre', 'level': 1},
    'lost_attachment'                       : {'instruction': "Pre migration needs to transfer byte data from the attachment table to the column.",                 "migration_semantic": 'pre', 'level': 1},
    'gained_selection'                      : {'instruction': "Nothing to do. It's part of an aggregate transition.",                                               "migration_semantic": None,  'level': 0},
    'lost_selection'                        : {'instruction': "Nothing to do. It's part of an aggregate transition.",                                               "migration_semantic": None,  'level': 0},
}

KNOWN_SCHEMA_AGGREGATE_TRANSITIONS_INSTRUCTIONS = {
    'moved_oldname'                         : {'instruction': "Nothing to do.",                                                                                     "migration_semantic": None,  'level': 0},
    'moved_mro_parallel'                    : {'instruction': "Pre migration will need to relocate the column.",                                                    "migration_semantic": 'pre', 'level': 1},
    'moved_exogenous'                       : {'instruction': "Pre migration will need to relocate the column. " + TABLE_RENAME_DEFINITION,                         "migration_semantic": 'pre', 'level': 1},
    # Casted type transitions
    'casted'                                : {'instruction': "Nothing to do.",                                                                                     "migration_semantic": None,  'level': 0},

    # None-Casted Type transitions
    'from_selection_to_many2one'            : {'instruction': "Pre migration will need to map selection char or int to foreign ids.",                               "migration_semantic": 'pre', 'level': 2},
    'from_many2one_to_selection'            : {'instruction': "Pre migration will need to map foreign ids to selecton char or int.",                                "migration_semantic": 'pre', 'level': 2},
    'from_selection_to_boolean'             : {'instruction': "Pre migration will need to map selection char or into to boolean values.",                           "migration_semantic": 'pre', 'level': 2},
    'from_boolean_to_selection'             : {'instruction': "Pre migration will need to map boolean values to selecton char or int.",                             "migration_semantic": 'pre', 'level': 2},
    'from_selection_to_char'                : {'instruction': "Pre migration will need to map selection int to char values (not casted).",                          "migration_semantic": 'pre', 'level': 2},
    'from_char_to_selection_casted'         : {'instruction': "Nothing to do. Sometimes casted selections can validate unintendetly: double check final result.",   "migration_semantic": None,  'level': 0},
    'from_char_to_selection_not_casted'     : {'instruction': "Pre migration will need to map char values to selection int (not casted).",                          "migration_semantic": 'pre', 'level': 2},
    'from_char_to_selection_invalid'        : {'instruction': "Pre migration will need to map int values to selection int (invalid).",                              "migration_semantic": 'pre', 'level': 2},
    'from_selection_to_integer'             : {'instruction': "Nothing to do. Sometimes casted selections can validate unintendetly: double check final result.",   "migration_semantic": None,  'level': 0},
    'from_integer_to_selection_casted'      : {'instruction': "Pre migration will need to map int values to selection char (not casted).",                          "migration_semantic": 'pre', 'level': 2},
    'from_integer_to_selection_not_casted'  : {'instruction': "Pre migration will need to map int values to selection char (not casted).",                          "migration_semantic": 'pre', 'level': 2},
    'from_integer_to_selection_invalid'     : {'instruction': "Pre migration will need to map char values to selection char (invalid).",                            "migration_semantic": 'pre', 'level': 2},

    'from_many2many_to_many2one'            : {'instruction': "Pre migration will need to homologate a single relational value into a new column.",                 "migration_semantic": 'pre', 'level': 2},
    'from_many2one_to_many2many'            : {'instruction': "Pre migration might need to shift single reference into rel table.",                                 "migration_semantic": 'pre', 'level': 1},

    'from_float_to_integer'                 : {'instruction': "Pre migration will need to round values.",                                                           "migration_semantic": 'pre', 'level': 1},
    'from_monetary_to_integer'              : {'instruction': "Pre migration will need to round values. (Note: it's suspicious a monetary field becomes integer)",  "migration_semantic": 'pre', 'level': 1},
    'from_binary_to_text_or_char_or_html'   : {'instruction': "Pre migration will need to decode binary data into string.",                                         "migration_semantic": 'pre', 'level': 1},
    'from_text_or_char_or_html_to_binary'   : {'instruction': "Pre migration will need to encode string into binary data.",                                         "migration_semantic": 'pre', 'level': 1},

    'not_known_not_casted'                  : {'instruction': "Pre migration needs to transform data in unconventional ways.",                                      "migration_semantic": 'pre', 'level': 2},

    # Same type transitions
    'char_shrinks'                          : {'instruction': "Pre migration will need to identify and trunkate oversized chars.",                                  "migration_semantic": 'pre', 'level': 2},
    'char_grows'                            : {'instruction': "Nothing to do.",                                                                                     "migration_semantic": None,  'level': 0},
    'selection_shrinks'                     : {'instruction': "Pre migration will need to homologate off values to existing ones.",                                 "migration_semantic": 'pre', 'level': 2},
    'selection_grows'                       : {'instruction': "Nothing to do.",                                                                                     "migration_semantic": None,  'level': 0},
}

KNOWN_SCHEMA_ATOMIC_TRANSITIONS = KNOWN_SCHEMA_ATOMIC_TRANSITIONS_DESCRIPTIONS
KNOWN_SCHEMA_ATOMIC_TRANSITIONS.update(KNOWN_SCHEMA_ATOMIC_TRANSITIONS_INSTRUCTIONS)
KNOWN_SCHEMA_AGGREGATE_TRANSITIONS = KNOWN_SCHEMA_AGGREGATE_TRANSITIONS_DESCRIPTIONS
KNOWN_SCHEMA_AGGREGATE_TRANSITIONS.update(KNOWN_SCHEMA_AGGREGATE_TRANSITIONS_INSTRUCTIONS)
# fmt: on
