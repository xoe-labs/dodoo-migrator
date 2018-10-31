# -*- coding: utf-8 -*-
# Copyright 2016-2017 Camptocamp SA
# Copyright 2017-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import click as _click


class _MigrationError(Exception):
    pass


class MigrationErrorUnfinished(_MigrationError):
    def __init__(self, unfinished):
        super(MigrationErrorUnfinished, self).__init__(unfinished)
        self.unfinished = unfinished

    def __str__(self):
        msg = (
            u"Upgrade of version {} has been attempted and failed. "
            u"You may want to restore the backup or to run again the "
            u"migration with the --force flag or to fix it manually "
            u"In that case, you will have to "
            u"update the  'click_odoo_migrator' table yourself.".format(self.unfinished)
        )
        return msg


class MigrationErrorGap(_MigrationError):
    def __init__(self, finished, since):
        super(MigrationErrorGap, self).__init__(finished, since)
        self.finished = finished
        self.since = since

    def __str__(self):
        msg = (
            u"The --since flag must specify the last executed migration. "
            u"Specifying a later migration would cause a igration gap. "
            u"Last finished version {}. "
            u"--since {}. ".format(self.finished, self.since)
        )
        return msg


class ParseError(_click.ClickException):
    def __init__(self, message, example=None):
        super(ParseError, self).__init__(message)
        self.example = example

    def __str__(self):
        if not self.example:
            return super(ParseError, self).__str__()
        msg = (
            u"An error occured during the parsing of the configuration "
            u"file. Here is an example to help you to figure out "
            u"your issue.\n{}\n{}"
        ).format(self.example, self.args[0])
        return msg
