# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import ast
import re

EXOGENOUS_INFORMATION_SUGGESTION = (
    "If for the body change, there can be construed a (simple) transformation "
    "function, consider to modify the known transformations file."
)


TARGET_RECORDS = {"noupdate": True}

BODY_FIELD_TYPES = ["char", "text", "html", "binary"]


# fmt: off
KOWN_TRANSITIONS_DESCRIPTIONS = {
    # Note: (column or model) relocations (refactorings) are covered by schema changes, so they are not of a concern here
    'disappear'                             : {'description': "Record X will disappear."},
    'body_change'                           : {'description': "Field X of record Y will change."},
}

KOWN_TRANSITIONS_INSTRUCTIONS = {
    'disappear'                             : {'instruction': "Post migrate might delete this record."},
    'body_change'                           : {'instruction': "Post migrate might execute a string transformation on this body." + EXOGENOUS_INFORMATION_SUGGESTION},
}


contains_something_like_a_model_string_regex = re.compile(r'[a-z0-9_.]+')

KNOWN_SUSPICIOUS_REGEX_DESCRIPTIONS = {
    'suspect_model'                         : {'description': "Record X field Y contains something that looks like a model reference",     'check': lambda string: bool(contains_something_like_a_model_string_regex.search(string))},
    'suspect_python'                        : {'description': "Record X field Y contains valid python code",                               'check': lambda string: is_valid_python(string)},
}


def is_valid_python(code):
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True

# fmt: on
