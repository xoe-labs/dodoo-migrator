# -*- coding: utf-8 -*-
# Copyright 2017-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import base64

import paramiko
import pysftp
import requests

from .errors import NotReadyError, NotUploadedError, OdooUpgradeServiceError

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

HOSTNAME = "upgrade.odoo.com"
CREATE_URL = "https://{}/database/v1/create".format(HOSTNAME)
UPLOAD_URL_SFTP = "https://{}/database/v1/request_sftp_access".format(HOSTNAME)
PROCESS_URL = "https://{}/database/v1/process".format(HOSTNAME)
STATUS_URL = "https://{}/database/v1/status".format(HOSTNAME)

HOSTKEY = (
    "upgrade.odoo.com",
    "ecdsa-sha2-nistp256",
    (
        b"AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbml"
        b"zdHAyNTYAAABBBE5mkrmHuWxgdBrxPF6iUArjMi"
        b"F5A1HtcyUsceIem56Gg5LYmxW97Vie5yzwRIFNs"
        b"qpLRP5AFOp7Jt6X6Ukv5Po="
    ),
)


class UpgradeApi(object):
    def __init__(self, name, aim, target, contract, email, public_key, private_key):
        self.name = name
        self.aim = aim
        self.target = target
        self.contract = contract
        self.email = email
        # Fix padding
        self.public_key = public_key
        self.private_key = private_key
        self.filename = "db.tar.gz"
        self._request = None
        self._request_id = None
        self._key = None
        self._request_sftp_access = None
        self._hostname = None
        self._sftp_port = None
        self._sftp_user = None
        self._process = None
        self._submitted = None
        self._ready = None

    def __repr__(self):
        return "{}({!r})".format(self.__class__, self.name)

    @property
    def request_id(self):
        if not self._request_id:
            self.request()
        return self._request_id

    @request_id.setter
    def request_id(self, value):
        self._request_id = value

    @property
    def key(self):
        if not self._key:
            self.request()
        return self._key

    @key.setter
    def key(self, value):
        self._key = value

    @property
    def hostname(self):
        if not self._hostname:
            self.request_sftp_access()
        return self._hostname

    @hostname.setter
    def hostname(self, value):
        self._hostname = value

    @property
    def sftp_port(self):
        if not self._sftp_port:
            self.request_sftp_access()
        return self._sftp_port

    @sftp_port.setter
    def sftp_port(self, value):
        self._sftp_port = value

    @property
    def sftp_user(self):
        if not self._sftp_user:
            self.request_sftp_access()
        return self._sftp_user

    @sftp_user.setter
    def sftp_user(self, value):
        self._sftp_user = value

    def request(self):
        if self._request:
            return
        payload = {
            "aim": self.aim,
            "email": self.email,
            "filename": self.filename,
            "contract": self.contract,
            "target": self.target,
        }
        r = requests.get(CREATE_URL, params=payload).json()
        if r.get("failure"):
            raise OdooUpgradeServiceError
        self._request = r.get("request")
        self._request_id = self._request.get("id")
        self._key = self._request.get("key")

    def request_sftp_access(self):
        if self._request_sftp_access:
            return
        payload = {"request": self.request_id, "key": self.key}
        data = {"ssh_keys": self.public_key}
        r = requests.post(UPLOAD_URL_SFTP, params=payload, data=data).json()
        if r.get("failure"):
            raise OdooUpgradeServiceError
        self._request_sftp_access = r.get("request")
        self._hostname = self._request_sftp_access.get("hostname")
        self._sftp_port = self._request_sftp_access.get("sftp_port")
        self._sftp_user = self._request_sftp_access.get("sftp_user")

    def upload(self, local_file_path):
        with pysftp.Connection(**self._cinfo()) as sftp:
            sftp.put(local_file_path, self.filename)
        self._submitted = True

    def process(self):
        if self._process:
            return
        if not self._submitted:
            raise NotUploadedError
        payload = {"request": self.request_id, "key": self.key}
        r = requests.get(PROCESS_URL, params=payload).json()
        if r.get("failure"):
            raise OdooUpgradeServiceError
        self._process = True

    def status(self):
        payload = {"request": self.request_id, "key": self.key}
        r = requests.get(STATUS_URL, params=payload).json()
        if r.get("failure"):
            raise OdooUpgradeServiceError
        return r.get("request")

    def is_ready(self):
        return self.status().get("state") == "done"

    def download(self, local_file_path):
        cinfo = self._cinfo()
        if not self.is_ready():
            raise NotReadyError
        with pysftp.Connection(**cinfo) as sftp:
            sftp.get(self.filename, local_file_path)

    def _cinfo(self):
        cnopts = pysftp.CnOpts()
        key = paramiko.ECDSAKey(data=base64.decodebytes(HOSTKEY[2]))
        cnopts.hostkeys.add(HOSTKEY[0], HOSTKEY[1], key)
        # https://github.com/paramiko/paramiko/issues/1015
        private_key = self.private_key.replace(
            b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----"
        ).replace(b"-----END PRIVATE KEY-----", b"-----END RSA PRIVATE KEY-----")
        return {
            "host": self.hostname,
            "username": self.sftp_user,
            "port": int(self.sftp_port),
            "private_key": paramiko.RSAKey(file_obj=StringIO(private_key.decode())),
            "cnopts": cnopts,
        }
