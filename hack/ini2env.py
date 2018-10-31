#!/usr/bin/env python

from __future__ import print_function

import sys

try:
    import ConfigParser as configparser
except ImportError:
    import configparser


CONFIG = configparser.ConfigParser()
CONFIG.readfp(sys.stdin)

ENV = []
for sec in CONFIG.sections():
    for key, val in CONFIG.items(sec):
        ENV.append('{}="{}"'.format(key, val))
        # print ENV[-1]

print(" \n".join(ENV))
