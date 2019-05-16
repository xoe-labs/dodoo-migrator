# -*- coding: utf-8 -*-
# Copyright 2017-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import gzip
import logging
import shutil
import tempfile
from contextlib import closing

import odoo

from . import keys, odoo_service

BOLD = u"\033[1m"
RESET = u"\033[0m"
GREEN = u"\033[1;32m"
BLUE = u"\033[1;34m"

_logger = logging.getLogger(BOLD + u"UPGRADE SERVICE" + RESET)


class DatabaseApi(object):
    def __init__(self, cr):
        self.cr = cr
        self._odoo_contract = None
        self._private_key = None
        self._public_key = None
        self._email = None
        self._sftp_hostname = None
        self._sftp_port = None
        self._sftp_user = None
        self._request = None
        self._token = None

    def _set_icp(self, key, value):
        key = getattr(type(self), key).__doc__
        self.cr.execute(
            """
            INSERT INTO ir_config_parameter(key, value)
            VALUES (%(key)s, %(value)s);
        """,
            locals(),
        )
        return value

    def _get_icp(self, key):
        key = getattr(type(self), key).__doc__
        self.cr.execute(
            """
            SELECT value FROM ir_config_parameter
            WHERE key = %(key)s;
        """,
            locals(),
        )
        r = self.cr.fetchone()
        return r[0] if r else ""

    @property
    def odoo_contract(self):
        """database.enterprise_code"""
        if self._odoo_contract:
            return self._odoo_contract
        self._odoo_contract = self._get_icp("odoo_contract")
        return self._odoo_contract

    @odoo_contract.setter
    def odoo_contract(self, value):
        self._odoo_contract = self._set_icp("odoo_contract", value)

    @property
    def private_key(self):
        """database.upgrade.operator.private_key"""
        if self._private_key:
            return self._private_key.encode("ascii")
        self._private_key = self._get_icp("private_key")
        if not self._private_key:
            self.public_key, self.private_key = keys.generate_key_pair()
        return self._private_key.encode("ascii")

    @private_key.setter
    def private_key(self, value):
        self._private_key = self._set_icp("private_key", value.decode())

    @property
    def public_key(self):
        """database.upgrade.operator.public_key"""
        if self._public_key:
            return self._public_key.encode("ascii")
        self._public_key = self._get_icp("public_key")
        if not self._public_key:
            self.public_key, self.private_key = keys.generate_key_pair()
        return self._public_key.encode("ascii")

    @public_key.setter
    def public_key(self, value):
        self._public_key = self._set_icp("public_key", value.decode())

    @property
    def email(self):
        if self._email:
            return self._email
        self.cr.execute(
            """
            SELECT email FROM res_company WHERE id = 1;
            """
        )
        r = self.cr.fetchone()
        self._email = r[0] if r else ""
        return self._email

    @property
    def sftp_hostname(self):
        """database.upgrade.service.sftp_hostname"""
        if self._sftp_hostname:
            return self._sftp_hostname
        self._sftp_hostname = self._get_icp("sftp_hostname")
        return self._sftp_hostname

    @sftp_hostname.setter
    def sftp_hostname(self, value):
        self._sftp_hostname = self._set_icp("sftp_hostname", value)

    @property
    def sftp_port(self):
        """database.upgrade.service.sftp_port"""
        if self._sftp_port:
            return self._sftp_port
        self._sftp_port = self._get_icp("sftp_port")
        return self._sftp_port

    @sftp_port.setter
    def sftp_port(self, value):
        self._sftp_port = self._set_icp("sftp_port", value)

    @property
    def sftp_user(self):
        """database.upgrade.service.sftp_user"""
        if self._sftp_user:
            return self._sftp_user
        self._sftp_user = self._get_icp("sftp_user")
        return self._sftp_user

    @sftp_user.setter
    def sftp_user(self, value):
        self._sftp_user = self._set_icp("sftp_user", value)

    @property
    def request(self):
        """database.upgrade.service.request_uid"""
        if self._request:
            return self._request
        self._request = self._get_icp("request")
        return self._request

    @request.setter
    def request(self, value):
        self._request = self._set_icp("request", value)

    @property
    def token(self):
        """database.upgrade.service.token"""
        if self._token:
            return self._token
        self._token = self._get_icp("token")
        return self._token

    @token.setter
    def token(self, value):
        self._token = self._set_icp("token", value)


def _sync_odoo(Db, Service):
    if Db.request and Db.token:
        Service.request_id = Db.request
        Service.key = Db.token
    else:
        Db.request = Service.request_id
        Db.token = Service.key

    if Db.sftp_hostname and Db.sftp_port and Db.sftp_user:
        Service.hostname = Db.sftp_hostname
        Service.sftp_port = Db.sftp_port
        Service.sftp_user = Db.sftp_user
    else:
        Db.sftp_hostname = Service.hostname
        Db.sftp_port = Service.sftp_port
        Db.sftp_user = Service.sftp_user


def submit(env, service, aim, target):
    with env.registry.cursor() as cr:
        Db = DatabaseApi(cr)
        if service == "odoo":
            Service = odoo_service.UpgradeApi(
                "DodooMigrator",
                aim,
                target,
                Db.odoo_contract,
                Db.email,
                Db.public_key,
                Db.private_key,
            )

            _logger.info(u"creating request ...")
            _sync_odoo(Db, Service)
            _logger.info(u"request %s created.", Db.request)
        cr.commit()

    f = gzip.open(tempfile.mktemp(), "wb")
    _logger.info(u"creating backup ...")
    _get_backup(env.cr.dbname, f)
    _logger.info(u"uploading ...")
    Service.upload(f.name)
    _logger.info(u"request processing...")
    Service.process()
    f.close()
    _logger.info(u"Now you need patience...")


def retrieve(env, service):
    f = tempfile.NamedTemporaryFile(mode="w+b")
    with env.registry.cursor() as cr:
        Db = DatabaseApi(cr)
        if service == "odoo":
            Service = odoo_service.UpgradeApi(
                "DodooMigrator",
                None,
                None,
                Db.odoo_contract,
                Db.email,
                Db.public_key,
                Db.private_key,
            )
            _logger.info(u"loading state from db ...")
            _sync_odoo(Db, Service)

    _logger.info(u"downloading ...")
    Service.download(f.name)
    _logger.info(u"restoring migrated ...")
    _drop_database(env.cr.dbname)
    _restore_backup(env.cr.dbname, f)


def _get_backup(db, f):
    cmd = ["pg_dump", "--no-privileges", "--no-owner", "--format=t", db]
    _, stdout = odoo.tools.exec_pg_command_pipe(*cmd)
    shutil.copyfileobj(stdout, f)


def _restore_backup(db, f):
    previous = odoo.tools.config["list_db"]
    odoo.tools.config["list_db"] = True
    t = tempfile.NamedTemporaryFile(mode="w+b")
    shutil.copyfileobj(f, t)
    odoo.service.db.restore_db(db, f.name, copy=False)
    odoo.tools.config["list_db"] = previous


def _drop_database(db_name):
    if db_name not in odoo.service.db.list_dbs(True):
        return False
    odoo.modules.registry.Registry.delete(db_name)
    odoo.sql_db.close_db(db_name)

    db = odoo.sql_db.db_connect("postgres")
    with closing(db.cursor()) as cr:
        cr.autocommit(True)  # avoid transaction block
        odoo.service.db._drop_conn(cr, db_name)

        try:
            cr.execute('DROP DATABASE "%s"' % db_name)
        except Exception as e:
            raise Exception("Couldn't drop database {}: {}".format(db_name, e))
