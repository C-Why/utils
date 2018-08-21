#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-------------------------------------------------
   Description :   This API is intended for internal Ansible use.
   Author :        C-Why
   date：          2018/7/18
-------------------------------------------------
"""
# WARN:
# 1.中文编码问题 sql导入
#   中文编码问题 ,shell 问题根源env 国家编码有关，sql 导入默认参数，系统env中的优先级 LC_ALL > LANG ，需要等于 en_US.UTF-8
#   源码根源，ansible.module_utils.basic
#   解决方法： 方法1.执行前，添加执行，export LC_ALL=en_US.UTF-8;
#             # TODO：方法2.import locale
#                    locale.setlocale(locale.LC_ALL,'en_US.UTF-8')

__author__ = r'C-Why'
__version__='0.0.1'

import time
from collections import namedtuple
from collections import defaultdict
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.playbook.play import Play
from ansible.executor.task_queue_manager import TaskQueueManager
import ansible.constants as C
from ansible.plugins.callback import CallbackBase
from ansible.executor.playbook_executor import PlaybookExecutor
import os
import sys
import json
import shutil
import structlog

# import locale
# locale.setlocale(locale.LC_ALL,'en_US.UTF-8')

logger =structlog.get_logger("ansible_api")
BASE_DIR=os.path.dirname(__file__)
TEMPLATE_DIR= BASE_DIR
Options = namedtuple('Options',
                     ['connection', 'module_path', 'forks', 'become', 'become_method', 'become_user', 'check',
                      'diff'])
class AnsibleApi(object):
    """
    This API is intended for internal Ansible use.
    """
    def __init__(self, resource, **kwargs):
        """
        :param resource:the inventory dirs, files, script paths or lists of hosts. e.g. '/etc/ansible/hosts'
        :param kwargs: ansible_ssh_user ansible_ssh_pass ansible_sudo_pass
        """
        # passwords: {'conn_pass': sshpass, 'become_pass': becomepass}
        self.passwords = self._get_validate_data(kwargs.get('passwords'),
                                                 dict())
        # initialize needed objects
        # Takes care of finding and reading yaml, json and ini files
        self.loader = self._get_validate_data(kwargs.get('loader'),
                                              DataLoader())
        self.resource = resource
        # create inventory, use path to host config file as source or hosts in a comma separated string
        self.inventory = self._get_validate_data(kwargs.get('inventory'),
                                                 InventoryManager(loader=self.loader, sources=self.resource))
        # since API is constructed for CLI it expects certain options to always be set, named tuple 'fakes' the args parsing options object
        # Options arg connection could be ['ssh',  'local']
        # become = ['sudo', 'su', 'pbrun', 'pfexec', 'runas', 'pmrun']
        self.options = self._get_validate_data(
                                            kwargs.get('options'),
                                            Options(connection='ssh', module_path='/path/to/mymodules', forks=10, become=None,
                                                    become_method=None, become_user=None, check=False,
                                                    diff=False)
                                               )
        # variable manager takes care of merging all the different sources to give you a unifed view of variables available in each context
        self.variable_manager = self._get_validate_data(kwargs.get('variable_manager'),
                                                        VariableManager(loader=self.loader, inventory=self.inventory))
        # 可设置账号密码进行ssh连接，对于run，这个设置是动态加载的
        ansible_ssh_user=kwargs.get('ansible_ssh_user')
        ansible_ssh_pass=kwargs.get('ansible_ssh_pass')
        ansible_sudo_pass=kwargs.get('ansible_sudo_pass')
        extra_vars=self.variable_manager.extra_vars
        if  ansible_ssh_user and ansible_ssh_pass:
            extra_vars.update(
            dict(ansible_ssh_user=ansible_ssh_user , ansible_ssh_pass=ansible_ssh_pass))
        if  ansible_sudo_pass:
            extra_vars.update(dict(ansible_sudo_pass=ansible_sudo_pass))
        # 指定解释器，为python3
        extra_vars.update(dict(ansible_python_interpreter='/usr/bin/env python3'))

        self.variable_manager.extra_vars=extra_vars
        # Instantiate our ResultCallback for handling results as they come in. Ansible expects this to be one of its main display outlets
        self.callback = self._get_validate_data(kwargs.get('callback'),
                                   ResultsCollector())
        # all the task to run, init tasks as []
        self.tasks=[]
        self.results_raw = {}

    @staticmethod
    def _get_validate_data(data, default_data):
        """对于预置数据是否存在，若存在，进行简单数据类型验证； 若不存在，赋予default_data"""
        if data :
            if type(data)!= type(default_data):
                raise ValueError("{} should be type {}".format(data, type(default_data)))
            else:
                return data
        return default_data

    # TODO：async_val,poll how to use it
    def add_task(self,task):
        # add task to run ， ansible.cli.adhoc
        #     tasks = [dict(
        #         action=dict(module=self.options.module_name, args=parse_kv(self.options.module_args, check_raw=check_raw)),
        #         async_val=async_val,
        #         poll=poll)]
        #
        # )
        self.tasks.append(task)

    def add_tasks(self,tasks):
        for module_name,module_args in tasks:
            self.add_task(module_name,module_args)

    def clear_tasks(self):
        self.tasks=[]

    def clear_result(self):
        self.callback.clear_result()

    def run(self, hosts,task=None, play_name="Ansible Play"):
        """
        run module from andible ad-hoc. module_name: ansible module_name module_args: ansible module args
        :param hosts: host group name,'all' 'webservers' 'dbservers'
        :return:
        """
        # create datastructure that represents our play, including tasks, this is basically what our YAML loader does internally.
        if task:
            tasks=[task]
        else:
            tasks =self.tasks
        play_source = dict(
            environment={'LC_ALL':'zh_CN.UTF-8','LANG':'zh_CN.UTF-8','LC_CTYPE':'zh_CN.UTF-8','PYTHONIOENCODING':'utf-8',
                         } ,
            name=play_name,
            hosts=hosts,
            gather_facts='no',
            tasks=tasks)
        play = Play().load(play_source, variable_manager=self.variable_manager, loader=self.loader)
        # Run it - instantiate task queue manager, which takes care of forking and setting up all objects to iterate over host list and tasks
        tqm = None
        try:
            tqm = TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variable_manager,
                loader=self.loader,
                options=self.options,
                passwords=self.passwords,
                stdout_callback=self.callback,       # Use our custom callback instead of the ``default`` callback plugin, which prints to stdout
            )
            result = tqm.run(play)
        finally:
            # we always need to cleanup child procs and the structres we use to communicate with them
            if tqm is not None:
                self.cleanup = tqm.cleanup()
            # Remove ansible tmpdir
            shutil.rmtree(C.DEFAULT_LOCAL_TMP, True)
            # 存在失败返回False
            result =self.get_result()
            if len(result.get('failed')) + len(result.get('unreachable')) > 0:
                return False
            return True

    # TODO: do not have enough time to 研究 it
    def run_playbook(self, host_list, role_name, role_uuid, temp_param):
        """
        run ansible palybook
        """
        try:
            filenames = [BASE_DIR + '/handlers/ansible/v1_0/sudoers.yml']
            #playbook的路径
            logger.info('ymal file path:%s'% filenames)
            template_file = TEMPLATE_DIR
            #模板文件的路径
            if not os.path.exists(template_file):
                logger.error('%s 路径不存在 '%template_file)
                sys.exit()

            extra_vars = {}      #额外的参数 sudoers.yml以及模板中的参数，它对应ansible-playbook test.yml --extra-vars "host='aa' name='cc' "
            host_list_str = ','.join([item for item in host_list])
            extra_vars['host_list'] = host_list_str
            extra_vars['username'] = role_name
            extra_vars['template_dir'] = template_file
            extra_vars['command_list'] = temp_param.get('cmdList')
            extra_vars['role_uuid'] = 'role-%s'%role_uuid
            self.variable_manager.extra_vars = extra_vars #
            # #logger.info('playbook 额外参数:%s'%self.variable_manager.extra_vars)
            #  actually run it
            executor = PlaybookExecutor(
                playbooks=filenames, inventory=self.inventory, variable_manager=self.variable_manager, loader=self.loader,
                options=self.options, passwords=self.passwords,
            )
            executor._tqm._stdout_callback = self.callback
            executor.run()
        except Exception as e:
            ##logger.error("run_playbook:%s"%e)
            pass

    def get_result(self):
        self.results_raw = {'success':{},
                            'failed':{},
                            'unreachable':{},}

        for host, result in self.callback.host_ok.items():
            self.results_raw['success'][host]=result
        for host, result in self.callback.host_failed.items():
            self.results_raw['failed'][host]=result
        for host, result in self.callback.host_unreachable.items():
            self.results_raw['unreachable'][host]=result

        return self.results_raw


class ResultsCollector(CallbackBase):
    """A sample callback plugin used for performing an action as results come in

        If you want to collect all results into a single object for processing at
        the end of the execution, look into utilizing the ``json`` callback plugin
        or writing your own custom callback plugin
        """
    def __init__(self, *args, **kwargs):
        super(ResultsCollector, self).__init__(*args, **kwargs)
        self.clear_result()
    def clear_result(self):
        self.host_ok = defaultdict(list)
        self.host_unreachable = defaultdict(list)
        self.host_failed = defaultdict(list)

    def v2_playbook_on_task_start(self, task, is_conditional):
        logger.debug('v2_playbook_on_task_start: {} {}'.format(task, task.args))

    def v2_runner_on_unreachable(self, result):
        self.host_unreachable[result._host.get_name()].append(result._result)
        host = result._host
        logger.error('v2_runner_on_unreachable: {}'.format(host.address))
        logger.error(json.dumps({host.name: result._result}, indent=4))

    def v2_runner_on_ok(self, result, *args, **kwargs):
        """Print a json representation of the result

        This method could store the result in an instance attribute for retrieval later
        """
        self.host_ok[result._host.get_name()].append(result._result)
        host = result._host
        logger.debug('v2_runner_on_ok: {}'.format(host.address))
        logger.debug(json.dumps({host.name: result._result}, indent=4))

    def v2_runner_on_failed(self, result, *args, **kwargs):
        self.host_failed[result._host.get_name()].append(result._result)
        host = result._host
        logger.error('v2_runner_on_failed: {}'.format(host.address))
        logger.error(json.dumps({host.name: result._result}, indent=4))

    # FIXME：: not called
    def v2_runner_on_async_poll(self, result):
        """异步处理，轮询"""
        host = result._host
        logger.debug('v2_runner_on_ok: {}'.format(host.address))
        logger.debug(json.dumps({host.name: result._result}, indent=4))

class Task(object):
    @classmethod
    def shell(cls,_raw_params,chdir=None,**kwargs):
        """shell 任务
        https://docs.ansible.com/ansible/latest/modules/shell_module.html"""
        module_kwargs = dict(_raw_params=_raw_params, **kwargs)
        if chdir:
            module_kwargs.update(dict(chdir=chdir))
        return cls.task('shell', module_kwargs)

    @classmethod
    def git(cls, repo, dest, version=None, **kwargs):
        """git拖取任务，远端到本地
        https://docs.ansible.com/ansible/latest/modules/git_module.html
        """
        module_kwargs=dict(repo=repo, dest=dest,**kwargs)
        if version:
            module_kwargs.update(dict(version=version))
        return cls.task('git',module_kwargs )

    @classmethod
    def copy(cls, src, dest=None, mode='777', **kwargs):
        """复制任务，本地到远端
        https://docs.ansible.com/ansible/latest/modules/copy_module.html
        """
        module_kwargs = dict(src=src, mode=mode, **kwargs)
        if dest:
            module_kwargs.update(dict(dest=dest))
        return cls.task('copy', module_kwargs)

    @classmethod
    def fetch(cls,src, dest, mode='777', **kwargs):
        """添加拖取任务，远端到本地
        https://docs.ansible.com/ansible/latest/modules/ping_module.html
        """
        return cls.task('fetch', dict(src=src, dest=dest, mode=mode, **kwargs))

    @classmethod
    def ping(cls,  **kwargs):
        """添加拖取任务，远端到本地
        https://docs.ansible.com/ansible/latest/modules/fetch_module.html
        """
        return cls.task('ping', dict(**kwargs))

    @staticmethod
    def task(module_name,module_kwargs=None,async_val=None,poll =None):
        """任务"""
        if not module_kwargs:
            module_kwargs = dict()
        kwargs = dict(action=dict(module=module_name, args=module_kwargs))
        if async_val:
            kwargs.update(dict(async_val=async_val))
        if poll:
            kwargs.update(dict(poll=poll))
        return kwargs


class Deploy(AnsibleApi):
    """部署，使用方式，可设置登录名称密码等参数，添加ansible 任务"""
    def __init__(self,ansible_ssh_user, ansible_ssh_pass,ansible_sudo_pass=None):
        # 是否使用sudo模式
        self.home=os.path.join("/home",ansible_ssh_user)
        if ansible_sudo_pass:
            options = Options(connection='ssh', module_path='/path/to/mymodules', forks=10, become=True,
                              become_method="sudo", become_user="root", check=False,
                              diff=False)
            super(Deploy, self).__init__(None, options=options, ansible_ssh_user=ansible_ssh_user,
                                         ansible_ssh_pass = ansible_ssh_pass, ansible_sudo_pass = ansible_sudo_pass)
        else:
            super(Deploy, self).__init__(None, ansible_sudo_pass=ansible_ssh_pass,
                                         ansible_ssh_user=ansible_ssh_user, ansible_ssh_pass=ansible_sudo_pass)


    def wait_for_reboot(self,reboot=False,retry=10,break_time=50):
        """添加等待重启任务，default 15~30"""
        if reboot:
            # 一分钟后重启
            cmd_line='shutdown -r +1'
            self.run(task=dict(action=dict(module='shell', args=cmd_line),async_val=0,poll =0))
            logger.info("{}，一分钟后重启".format(cmd_line))
            time.sleep(65)
        for i in range(retry):
            logger.info("等待设备启动{}/{}，最大等待时间{}s".format(i+1,retry,break_time))
            self.clear_result()
            self.run(task=dict(action=dict(module='ping'),async_val=0,poll =0))
            print("result: {}".format(self.get_result()))
            if self.get_result().get('success'):
                return True
            else:
                logger.info("sleep {}S".format(break_time))
                time.sleep(break_time)

        return False

    def add_host(self,host,group="all"):
        """
        添加host，可以是ip 或者url，省去group，port
        :param host: ip or url
        :return:
        """
        self.inventory.add_host(host,group)

    def run(self, hosts='all',task=None):
        """默认运行所有host"""
        return super(Deploy, self).run(hosts=hosts,task=task)

    def run_simple(self,task,hosts='all'):
        """简单模式"""
        # 原来模式比较复杂，简化，实现单步骤
        self.clear_result()
        return self.run(hosts=hosts,task=task)


def rsa():
    # 手動設置了ssh密鑰
    # 传入inventory路径
    ansible = AnsibleApi('/etc/ansible/hosts')
    # 添加task：获取服务器磁盘信息
    bin_path="/IFaaS/chenyu/ansible/all-v1.5.2-ci.bin"
    log_path="~/install_all-v1.5.2-ci.bin.log"
    ansible.add_tasks(
        [('copy',dict(src=bin_path,dest ='~/',mode='777')),
         ('shell', 'sudo ./all-v1.5.2-ci.bin > {}'.format(log_path)),
         ('fetch',dict(src=log_path,dest ='/IFaaS/chenyu/ansible/',mode='777')),
         ],
    )
    ansible.run('192.168.11.98', )

def on_line():
    # 即时传输用户名，密码参数
    # 使用ssh连接时首次连接需要输入yes/no部分，通过设置ansible.cfg，避免这种情况。一下方式任一个均可：
    #
    #设置一###############################################
    #  uncomment this to disable SSH key host checking
    #  host_key_checking = False
    #####################################################
    #
    #设置二############################################################################
    # ssh arguments to use
    # Leaving off ControlPersist will result in poor performance, so use
    # paramiko on older platforms rather than removing it, -C controls compression use
    # ssh_args = -C -o ControlMaster=auto -o ControlPersist=60s
    ###################################################################################
    user_name='intellif'
    password='introcks'
    # 在这里不使用hosts文件，手动添加host
    ansible = AnsibleApi(None,ansible_ssh_user=user_name,ansible_ssh_pass=password)
    #  所有的hosts： ansible.inventory.hosts
    ansible.inventory.add_host('192.168.11.98')
    ansible.add_task('shell','ls')
    ansible.run(['192.168.11.98'])


def deploy_reboot():
    # 重启等待
    user_name = 'XXXXX'
    password = 'XXXXX'
    d =Deploy(user_name, password,password)
    d.add_host('XXX.XXX.XXX.XXX')
    result=d.wait_for_reboot(reboot=True)
    print(result)


def deploy_install():
    user_name = 'XXX'
    password = 'XXX'
    d = Deploy(user_name, password, password)
    d.add_host('XXX.XXX.XXX.XXX')
    src='/XXX/.../XXX.bin'
    log_name='install_{}.log'.format(os.path.basename(src))
    home_dir='/home/{}/'.format(user_name)
    remote_dir = '/home/{}'.format(user_name)
    log_path = os.path.join(remote_dir,log_name)
    remote_bin = "{}/{}".format(remote_dir, os.path.basename(src))
    d.add_task(Task.copy(src,dest=home_dir))
    # 中文编码问题处理
    d.add_task(Task.shell(_raw_params='export LC_ALL=en_US.UTF-8;sudo {} > {}'.format(remote_bin, log_path),chdir=home_dir))
    d.add_task(Task.fetch(src=log_path, dest='/XXX/XXX/XXX/'))
    d.run()

    d.wait_for_reboot()
    print('done')

def check_ansible_git():
    """测试git"""
    repo='XXXXX'
    dest='/opt/'
    device_ip='XXX.XXX.XXX.XXX'
    device_user = 'XXX'
    device_password = 'XXX'
    deploy_handle = Deploy(ansible_ssh_user=device_user, ansible_sudo_pass=device_password,
                           ansible_ssh_pass=device_password)
    deploy_handle.add_host(device_ip)
    result =deploy_handle.run_simple(Task.git(repo=repo,dest=dest))
    print(json.dumps(result,indent=4))



if __name__ == '__main__':
    # deploy_reboot()
    # deploy_install()
    check_ansible_git()