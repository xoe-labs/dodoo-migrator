# -*- coding: utf-8 -*-
# Copyright 2017-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


class Error(Exception):
    """Base class for exceptions in this module."""

    pass


class OdooUpgradeServiceError(Error):
    """Exception raised for failures returned from the odoo upgrade service.
    """

    pass


class NotUploadedError(Error):
    pass


class NotReadyError(Error):
    pass
