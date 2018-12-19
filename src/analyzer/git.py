# -*- coding: utf-8 -*-
# Copyright 2018-2018 XOE Corp. SAS
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

import subprocess

import click


class Git(object):
    def __enter__(self):
        self.head = self.get_branch_name()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.checkout(self.head)

    def __init__(self, git_dir):
        self.git_dir = git_dir
        self.head = None
        click.echo("==> Git-Dir: %s" % self.git_dir)

    def run(self, command):
        """Execute git command in bash
        :param list command: Git cmd to execute in self.git_dir
        :return: String output of command executed.
        """
        cmd = ["git", "--git-dir=" + self.git_dir] + command
        try:
            click.echo(">>> " + " ".join(cmd))
            res = subprocess.check_output(cmd)
        except subprocess.CalledProcessError:
            res = None
        if isinstance(res, bytes):
            res = res.decode("utf-8")
        if res:
            res = res.strip("\n")
        return res

    def checkout(self, branch):
        command = ["checkout", "--recurse-submodules", branch]
        res = self.run(command)
        if res is None:
            ctx = click.get_current_context()
            ctx.fail("Checkout failed. Aborting for security.")

    def get_branch_name(self):
        """Get branch name
        :return: String with name of current branch name"""
        command = ["rev-parse", "--abbrev-ref", "HEAD"]
        return self.run(command)
