# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import sys
from collections import OrderedDict

import odoo
import pandas
import yaml

from ..env import OdooAnalyzerEnvironment
from ..git import Git
from ._exceptions import ExtraColumnsException

DB_PREFIX = "dodoo-migrator-analyzer-temporary-branch-"

LIB_UPDATE_STR = "The analyzer package might need an update to handle this properly."


def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
    # This won't be necesary after python 3.7:
    # https://stackoverflow.com/a/21912744
    # "In python 3.7+, the insertion-order preservation nature of dict objects
    # has been declared to be an official part of the Python language spec"
    class OrderedLoader(Loader):
        pass

    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))

    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
    )
    return yaml.load(stream, OrderedLoader)


def get_dataframe_of_all_fields(registry):
    rows = []
    for model in registry.models:
        for field in model._fields:
            row = {}
            row["index"] = field.name.__str__()
            attributes = (
                # all slots of field type
                list(type(field)._slots.keys())
                # all non-slot attributes of field instance
                + list(field._attrs.keys())
            )
            for attr in attributes:
                # filter out dict containing non-slot attributes
                if attr == "_attrs":
                    continue
                if attr == "_modules":
                    # make set order relevant entropy in panda equality check
                    # _modules order representes the inverse mro
                    # list type also enables slicing
                    row[attr] = list(attr)
                    row["_origin_module"] = attr[-1]
                    continue
                row[attr] = field.__getattribute__(attr)

    return pandas.DataFrame.from_dict(rows, index="index")


class SchemaAnalyzer(object):
    """ Analyzes and compares Odoo registries of different code bases for their
    schema changes """

    def __init__(
        self,
        git_dir,
        old_branch,
        new_branch,
        exogenous_information_file=None,
        environment_manager=OdooAnalyzerEnvironment,
    ):
        # TODO: wire PYTHOPATH + GIT_DIR together to present a consistent source
        self.git_dir = git_dir
        sys.path = [git_dir] + sys.path
        self.old_branch = old_branch
        self.old_branch_db_name = DB_PREFIX + old_branch
        self.new_branch = new_branch
        self.new_branch_db_name = DB_PREFIX + new_branch
        (
            self.model_renames,
            self.field_renames,
            self.field_ignores,
        ) = self._parse_exogenous_information(exogenous_information_file)
        self.old_fields_df = pandas.DataFrame
        self.new_fields_df = pandas.DataFrame
        self.environment_manager = environment_manager

    def _load(self):
        """ Loads fields dataframes of both codebases"""
        with Git(git_dir=self.git_dir) as git:

            # Load analysis from old branch codebase
            git.checkout(self.old_branch)
            with self.environment_manager(self.old_branch_db_name) as env:
                self.old_fields_df = get_dataframe_of_all_fields(env.registry)

            # Load analysis from new branch codebase
            git.checkout(self.new_branch)
            with self.environment_manager(self.new_branch_db_name) as env:
                self.new_fields_df = get_dataframe_of_all_fields(env.registry)

    def _validate_exogenous_information(self, exogenous_information_dict):
        # No split check already done by yaml validation?
        # Check source and target are valid in model_renames and field_renames
        # Suggest module rename if all non-magic fields are moved
        # Check field_ignores does not cross with field_renames (ignores preced)
        return exogenous_information_dict

    def _normalize_exogenous_information(self, exogenous_information_dict):
        model_renames = exogenous_information_dict["model_renames"]
        field_renames = exogenous_information_dict["field_renames"]
        field_ignores = exogenous_information_dict["field_ignores"]
        return model_renames, field_renames, field_ignores

    def _parse_exogenous_information(self, exogenous_information_file):
        f_obj = open(exogenous_information_file, "rb")
        file_byte_content = f_obj.read()
        exogenous_information_dict = ordered_load(file_byte_content)
        exogenous_information_dict = self._validate_exogenous_information(
            exogenous_information_dict
        )
        model_renames, field_renames, field_ignores = self._normalize_exogenous_information(  # noqa: B950
            exogenous_information_dict
        )
        return model_renames, field_renames, field_ignores

    def _compare(self, selection_group=4):
        """ Compares panda dataframes for changes on the attributes
        included by the selection_group, also takes exogenous known information
        into account to reduce the diff """
        df1 = self.old_fields_df
        df2 = self.new_fields_df

        # Step 1:  Normalize indices and store delta
        # Step 1a: drop ignored fields on both, old and new dataframes
        df1 = df1.drop(self.field_ignores)
        df2 = df2.drop(self.field_ignores)
        # Step 1bi: inject exogenous relocation information (model renames)
        index = df1.index
        for source, target in self.model_renames.items():
            index = index.str.replace("^" + source, target, regex=True)
        df1.index = index
        # Step 1bii: inject exogenous relocation information (field renames)
        df1 = df1.rename(index=self.field_renames)
        rows = df1.index & df2.index
        df1_extra_rows = rows ^ df1.index
        df2_extra_rows = rows ^ df2.index

        # Step 2:  Normalize columns and store delta.
        # Step 2a: inject known column renames
        df1 = df1.rename(columns=dict(odoo.fields.RENAMED_ATTRS))
        columns = df1.columns & df2.columns
        df1_extra_columns = columns ^ df1.columns
        df2_extra_columns = columns ^ df2.columns
        # FIXME: Due to the dynamic nature of attribute analysis, in rare cases
        # it can happen that extra columns do not representing a schema change
        # Example: DF with single row Char that becomes Many2many (extra slots)
        if df1_extra_columns:
            raise ExtraColumnsException(
                "The old schema has extra attributes "
                "not known in the new schema. " + LIB_UPDATE_STR
            )
        if df2_extra_columns:
            raise ExtraColumnsException(
                "The new schema has extra attributes "
                "not known in the old schema. " + LIB_UPDATE_STR
            )

        # Step 3:  Compare normalized dataframes
        changed = df1.loc[rows, columns] != df2.loc[rows, columns]
        df1_changed = df1.loc[rows, columns][changed]
        df2_changed = df2.loc[rows, columns][changed]

        # Example:
        # >>> df1.loc[rows,columns][changed]
        #        boolean       list  set
        # index
        # row1       NaN        NaN  NaN
        # row2       NaN  [1, 2, 3]  NaN
        # >>> df2.loc[rows,columns][changed]
        #        boolean       list  set
        # index
        # row1       NaN        NaN  NaN
        # row2       NaN  [3, 2, 1]  NaN

        # Step 4:  Identify known transitinos and hanlde unkowns
        print(df1_extra_rows)
        print(df2_extra_rows)
        print(df1_changed)
        print(df2_changed)


# 0. define receiving data structures for field spec of both branches
# 1. execute subroutine on two branches
# # 1. checkout branch (recursively)
# # 2. start odoo environment
# # 3. run get_dataframe_of_all_fields
# # 4. stop odoo environment
# 2. return a diff data frame with changed rows
