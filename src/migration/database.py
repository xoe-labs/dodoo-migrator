# -*- coding: utf-8 -*-
# Copyright 2016-2017 Camptocamp SA
# Copyright 2017-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import json
from collections import namedtuple


class MigrationTable(object):
    def __init__(self, env):
        self.env = env
        self.table_name = "click_odoo_migrator"
        self.VersionRecord = namedtuple(
            "VersionRecord", "number app_version date_start date_done operations"
        )
        self._versions = None
        self._create_if_not_exists()

    def _create_if_not_exists(self):
        with self.env.registry.cursor() as cursor:
            query = """
            CREATE TABLE IF NOT EXISTS {} (
                number VARCHAR NOT NULL,
                app_version VARCHAR NOT NULL,
                date_start TIMESTAMP NOT NULL,
                date_done TIMESTAMP,
                operations TEXT,

                CONSTRAINT version_pk PRIMARY KEY (number)
            );
            """.format(
                self.table_name
            )
            cursor.execute(query)

    def versions(self):
        """ Read versions from the table

        The versions are kept in cache for the next reads.
        """
        if self._versions is not None:
            return self._versions
        with self.env.registry.cursor() as cursor:
            query = """
            SELECT number,
                   app_version,
                   date_start,
                   date_done,
                   operations
            FROM {}
            """.format(
                self.table_name
            )
            cursor.execute(query)
            rows = cursor.fetchall()
            versions = []
            for row in rows:
                row = list(row)
                # convert 'operations' to json
                row[4] = json.loads(row[4]) if row[4] else []
                versions.append(self.VersionRecord(*row))
            self._versions = versions
        return self._versions

    def start(self, version, app_version, timestamp):
        with self.env.registry.cursor() as cursor:
            query = """
            INSERT INTO {}
            (number, app_version, date_start)
            VALUES (%s, %s, %s)
            """.format(
                self.table_name
            )
            cursor.execute(query, (version, app_version, timestamp))
        self._versions = None  # reset versions cache

    def finish(self, version, timestamp, operations):
        with self.env.registry.cursor() as cursor:
            query = """
            UPDATE {}
            SET date_done = %s,
                operations = %s
            WHERE number = %s
            """.format(
                self.table_name
            )
            cursor.execute(query, (timestamp, json.dumps(operations), version))
            self._versions = None  # reset versions cache
