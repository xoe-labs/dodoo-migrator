# -*- coding: utf-8 -*-
# Copyright 2016-2017 Camptocamp SA
# Copyright 2017-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import json
from collections import namedtuple

import semver


class MigrationTable(object):
    def __init__(self, conn):
        self.conn = conn
        self.table_name = "dodoo_migrator"
        self._versions = None
        self._create_if_not_exists()

    def _create_if_not_exists(self):
        with self.conn.cursor() as cursor:
            query = """
            CREATE TABLE IF NOT EXISTS {} (
                number VARCHAR NOT NULL,
                app_version VARCHAR NOT NULL,
                date_start TIMESTAMP NOT NULL,
                date_done TIMESTAMP,
                operations TEXT,
                service VARCHAR,

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
        VersionRecord = namedtuple(
            "VersionRecord",
            "number app_version date_start date_done operations service",
        )
        if self._versions is not None:
            return self._versions
        with self.conn.cursor() as cursor:
            query = """
            SELECT number,
                   app_version,
                   date_start,
                   date_done,
                   operations,
                   service
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
                # parse number to semver
                row[0] = semver.parse_version_info(row[0])
                versions.append(VersionRecord(*row))
            self._versions = versions
        return self._versions

    def start(self, version, app_version, timestamp, service):
        with self.conn.cursor() as cursor:
            query = """
            INSERT INTO {}
            (number, app_version, date_start, service)
            VALUES (%s, %s, %s, %s)
            """.format(
                self.table_name
            )
            cursor.execute(query, (version, app_version, timestamp, service))
        self._versions = None  # reset versions cache

    def finish(self, version, timestamp, operations):
        with self.conn.cursor() as cursor:
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
