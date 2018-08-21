#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-------------------------------------------------
   Description :Copy from ansible.
   Author :        C-Why
   date：          2018/7/3
-------------------------------------------------
"""
# Copy from ansible.
from __future__ import (absolute_import, division, print_function)
__author__ = r'C-Why'
__metaclass__ = type

import os
import select
import shlex
import subprocess
import sys
from tempfile import NamedTemporaryFile

from six import PY2, PY3
from utils._text import to_bytes

from utils.logger import log

IS_WINDOWS = (os.name == 'nt')
CODE_UTF8='utf-8'

def bytes_2_lines(bytes,tail,log_need=True):
    """"""
    text = bytes.decode(CODE_UTF8,errors="ignore")
    lines = text.split("\n")
    if len(lines) == 1:
        tail = lines[0]
    else:
        lines[0] = tail + lines[0]
        tail = lines[-1]
        if log_need:
            for line in lines[:-1]:
                log.info(line)
    return lines,tail


def run_cmd(cmd, cwd_path=False,log_need=True ,live=False, readsize=100):

    # readsize = 10

    # On python2, shlex needs byte strings
    if PY2:
        cmd = to_bytes(cmd, errors='surrogate_or_strict')
    cmdargs = shlex.split(cmd)

    # subprocess should be passed byte strings.  (on python2.6 it must be
    # passed byte strtings)

    # windows need: shell = True
    if cwd_path:
        if os.path.exists(cwd_path):
            os.chdir(cwd_path)
        else:
            raise FileNotFoundError("run_cmd cwd_path")
        if log_need:
            log.info("cwd_path done",cwd_path=cwd_path)

    if IS_WINDOWS:
        p = subprocess.Popen(cmdargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE,shell=True)
    else :
        # for windows not need to to_bytes
        cmdargs = [to_bytes(a, errors='surrogate_or_strict') for a in cmdargs]
        p = subprocess.Popen(cmdargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if log_need:
        log.info('cmd args:',Popen=shlex.split(cmd))

    stdout = b''
    stderr = b''
    rpipes = [p.stdout, p.stderr]
    #
    tail=""
    while True:

        # *** IMPORTANT NOTICE ***
        #     On Windows, only sockets are supported; on Unix, all file
        #     descriptors can be used.
        rfd, wfd, efd = select.select(rpipes, [], rpipes, 1)

        if p.stdout in rfd:
            dat = os.read(p.stdout.fileno(), readsize)

            if live:
                # On python3, stdout has a codec to go from text type to bytes
                if PY3:
                    sys.stdout.buffer.write(dat)

                else:
                    sys.stdout.write(dat)
            if log_need:
                lines,tail=bytes_2_lines(dat,tail)

            stdout += dat
            if dat == b'':
                rpipes.remove(p.stdout)
        if p.stderr in rfd:
            dat = os.read(p.stderr.fileno(), readsize)
            stderr += dat
            if live:
                # On python3, stdout has a codec to go from text type to bytes
                if PY3:
                    sys.stdout.buffer.write(dat)
                else:
                    sys.stdout.write(dat)
            if log_need:
                lines, tail = bytes_2_lines(dat, tail,log_need=True)

            if dat == b'':
                rpipes.remove(p.stderr)

        # only break out if we've emptied the pipes, or there is nothing to
        # read from and the process has finished.
        if (not rpipes or not rfd) and p.poll() is not None:
            break
        # Calling wait while there are still pipes to read can cause a lock
        elif not rpipes and p.poll() is None:
            p.wait()

    return p.returncode, stdout.decode('utf-8',errors='ignore'), stderr.decode('utf-8',errors='ignore')

def run_cmd_plus(cmd,cwd_path=False,log_need=True ,live=False, readsize=100):

    # readsize = 10

    # On python2, shlex needs byte strings
    if PY2:
        cmd = to_bytes(cmd, errors='surrogate_or_strict')
    cmdargs = shlex.split(cmd)

    # subprocess should be passed byte strings.  (on python2.6 it must be
    # passed byte strtings)

    # windows need: shell = True
    if cwd_path:
        if os.path.exists(cwd_path):
            os.chdir(cwd_path)
        else:
            raise FileNotFoundError("run_cmd cwd_path")
        if log_need:
            log.info("cwd_path done",cwd_path=cwd_path)

    if IS_WINDOWS:
        p = subprocess.Popen(cmdargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE,shell=True)
    else :
        # for windows not need to to_bytes
        cmdargs = [to_bytes(a, errors='surrogate_or_strict') for a in cmdargs]
        p = subprocess.Popen(cmdargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if log_need:
        log.info('cmd args:',Popen=shlex.split(cmd))

    # 随机创建，临时文件保存log，关闭后不删除
    stdout_file = NamedTemporaryFile(mode='ab',prefix='stdout_',delete=False,dir='/IFaaS/chenyu/tmp')
    stdout_file.close()
    stderr_file = NamedTemporaryFile(mode='ab',prefix='stderr_',delete=False,dir='/IFaaS/chenyu/tmp')
    stderr_file.close()
    rpipes = [p.stdout, p.stderr]
    #
    tail=""
    while True:

        # *** IMPORTANT NOTICE ***
        #     On Windows, only sockets are supported; on Unix, all file
        #     descriptors can be used.
        rfd, wfd, efd = select.select(rpipes, [], rpipes, 1)

        if p.stdout in rfd:
            dat = os.read(p.stdout.fileno(), readsize)

            if live:
                # On python3, stdout has a codec to go from text type to bytes
                if PY3:
                    sys.stdout.buffer.write(dat)

                else:
                    sys.stdout.write(dat)
            if log_need:
                lines,tail=bytes_2_lines(dat,tail)
            # 写进，标准log
            with open(stdout_file.name, 'ab') as stdout:
                stdout.write(dat)
            if dat == b'':
                rpipes.remove(p.stdout)
        if p.stderr in rfd:
            dat = os.read(p.stderr.fileno(), readsize)
            # 写进，错误log
            with open(stderr_file.name, 'ab') as stderr:
                stderr.write(dat)
            if live:
                # On python3, stdout has a codec to go from text type to bytes
                if PY3:
                    sys.stdout.buffer.write(dat)
                else:
                    sys.stdout.write(dat)
            if log_need:
                lines, tail = bytes_2_lines(dat, tail,log_need=True)

            if dat == b'':
                rpipes.remove(p.stderr)

        # only break out if we've emptied the pipes, or there is nothing to
        # read from and the process has finished.
        if (not rpipes or not rfd) and p.poll() is not None:
            break
        # Calling wait while there are still pipes to read can cause a lock
        elif not rpipes and p.poll() is None:
            p.wait()

    return p.returncode, stdout_file.name, stderr_file.name


def exam():
    # success: returncode == 0
    cmd_line ="ls"
    returncode,stdout,stderr=run_cmd(cmd_line)
    print(returncode,stdout,stderr)
    # failed: returncode != 0
    cmd_line = "ls errorerror"
    returncode, stdout, stderr = run_cmd(cmd_line)
    print(returncode, stdout, stderr)

def exam_plus():
    cmd_line = "ls -R /"
    returncode,stdout_path,stderr_path=run_cmd_plus(cmd_line)
    print(returncode,stdout_path,stderr_path)

def cppcheck():
    # cmd_line="cppcheck --enable=all IFaceEngine"
    cmd_line="cppcheck --xml IFaceEngine"
    returncode, stdout_path, stderr_path = run_cmd_plus(cmd_line)
    print(returncode, stdout_path, stderr_path)

if __name__ == '__main__':
    # exam()
    # exam_plus()
    cppcheck()