#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-------------------------------------------------
   Description :
   Author :        C-Why
   date：          2018/7/6
-------------------------------------------------
"""
__author__ = r'C-Why'

from structlog import wrap_logger
import logging

from structlog.dev import ConsoleRenderer, _has_colorama
from structlog.processors import StackInfoRenderer, format_exc_info

_BUILTIN_DEFAULT_PROCESSORS = [
    StackInfoRenderer(),
    format_exc_info,
    ConsoleRenderer(colors=_has_colorama),
]


log = wrap_logger(logging.getLogger("utils").setLevel(logging.DEBUG), processors=_BUILTIN_DEFAULT_PROCESSORS, context_class=dict)

def print_all_log():
    log.info("info log")
    log.debug("debug log")
    log.error("eroor log")
    log.critical("critical log")

    log.info("has kwargs: ",a="a",b="b")

if __name__ == '__main__':
    print_all_log()

