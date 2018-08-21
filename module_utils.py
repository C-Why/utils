#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-------------------------------------------------
   Description :源代码管理，git
   Author :        C-Why
   date：          2018/6/20
-------------------------------------------------
"""
__author__ = r'C-Why'
__version__='0.0.0'
import os
import shutil
from git import Repo
from git.exc import (
    InvalidGitRepositoryError,
    NoSuchPathError,
    BadName,
)
from git import RemoteProgress
from collections import OrderedDict

from utils.logger import log


def progress_bar(percent,tail,print_need=False):
    """进程条
    100.00% |████████████████████████████████| 还剩:0.0 S"""
    if type(percent) != int and type(percent) != float or percent >1:
        log.info(tail)
        return
    block_full = chr(9608)
    piece_types = [chr(b) for b in range(9615, 9607, -1)]
    piece_types.insert(0,"")
    size_of_pieces_type = len(piece_types)
    num_of_blocks_total = 32
    num_of_pieces_total = num_of_blocks_total * size_of_pieces_type
    num_of_blocks=(int(num_of_pieces_total*percent)//size_of_pieces_type)*block_full
    cur_block=piece_types[int(num_of_pieces_total*percent)%size_of_pieces_type]
    if print_need:
        print("\r{:.2%} |{}{}| {}".format(percent,num_of_blocks,cur_block,tail), end="")
    log.info("{:.2%} |{}{}| {}".format(percent,num_of_blocks,cur_block,tail))


class MyProgressPrinter(RemoteProgress):
    def update(self, op_code, cur_count, max_count=None, message=''):
        percent=cur_count /(max_count or 100.0)
        msg ="git progress {} {} {} {} {}".format(op_code,cur_count,max_count,"{:.2%}".format(percent) ,message or 'NO MESSAGE')
        # log.info(msg)
        op_name_cur=[]
        op_name_types=['BEGIN', 'END', 'COUNTING', 'COMPRESSING', 'WRITING','RECEIVING', 'RESOLVING', 'FINDING_SOURCES', 'CHECKING_OUT']
        op_code_types=[1 << x for x in range(len(op_name_types))]
        for op_name_type,op_code_type in zip(op_name_types,op_code_types):
            if op_code & op_code_type:
                op_name_cur.append(op_name_type)
        op_name_cur=" ".join(op_name_cur)
        tail = "{} {}/{} | {}".format(op_name_cur,cur_count,max_count,message or "")
        progress_bar(percent,tail)


class SourceCode(object):
    """
    源代码管理，git
    """
    MASTER_BRANCH_NAME="master"
    REMOTE ="origin"
    def __init__(self, repository_url, parent_dir, branch_2_build, base_dir=None):
        """
        :param repository_url:存储地址
        :param parent_dir:本地父目录，指定base_dir或者根据repository_url截取
        :param branch_2_build:需要pull的代码分支
        :param base_dir:默认不使用base_dir，根据repository_url截取定义parent_dir下级目录
        """
        self.repository_url = repository_url
        if base_dir:
            self.build_dir = os.path.join(parent_dir, base_dir)
        else:
            self.build_dir = os.path.join(parent_dir, os.path.basename(self.repository_url).split('.git')[0])
        # 对应的分支，没有提供，则使用master
        if branch_2_build:
            self.branch_2_build = branch_2_build
        else:
            self.branch_2_build = self.MASTER_BRANCH_NAME
        self._cur_sha=None

    def git_repo_object(self, init_not_exists=True):
        """获取git repository对象，路径为<self.build_dir>"""
        if not os.path.exists(self.build_dir) and init_not_exists:
            # 如果build_dir不存在，并需要init
            self.git_init(remove=False)
            self.git_fetch()
        try:
            repo = Repo(self.build_dir)
            return repo
        except InvalidGitRepositoryError as e:
            log.error("无效git  repository：{}".format(self.build_dir))
            raise e
        except NoSuchPathError as e:
            log.error("目录不存在：{}".format(self.build_dir))
            raise e

    def git_init(self, remove=True):
        """初始化git repository, 默认删除目录如果存在
        git init"""
        if os.path.exists(self.build_dir):
            if remove:
                shutil.rmtree(self.build_dir)
            else:
                return
        Repo.init(self.build_dir)

    @property
    def git_cur_sha(self):
        return self._cur_sha

    def new_commits(self,branch=None,cur_commit_hexsha=None):
        """cur_commit_hexsha最的所有commit数据
        commit.authored_date,  commit.committed_date,   commit.authored_datetime,  commit.committed_datetime
        commit.author.name,  commit.author.email,  commit.hexsha,  commit.message.strip()
        """
        if not branch:
            branch = self.branch_2_build
        self.git_local_update_remote()
        repo = self.git_repo_object()
        commits=[]
        ref = "refs/remotes/{}/{}".format(self.REMOTE, branch)
        rev = "{}^{{commit}}".format(ref)
        try:
            iter_commits= repo.iter_commits(rev=rev)
            for commit in iter_commits:
                if commit.hexsha==cur_commit_hexsha:
                    break
                commits.append(commit)
        except Exception as e:
            log.error("all_commit:{}".format(e))
            return []
        return commits

    def git_last_commit(self,branch=None):
        """<branch>最后一次的commit数据类型"""
        if not branch:
            branch=self.branch_2_build
        self.git_local_update_remote()
        ref = "refs/remotes/{}/{}".format(self.REMOTE,branch)
        rev = "{}^{{commit}}".format(ref)
        repo = self.git_repo_object()
        try:
            # commit 类型：git.objects.commit.Commit
            # 用户名，用户邮件  commit.author.name，commit.author.email
            # hexsha：commit.hexsha
            # commit.authored_datetime, commit.authored_date
            # commit message：commit.message
            commit = repo.rev_parse(rev)
            return commit
        except BadName as e:
            log.error("ref {} 不存在或者其他错误，无法生成对应对象object".format(ref))
            raise e

    def git_checkout(self, commit_hexsha, branch="", force=True):
        """checkout 某个点<commit_hexsha>"""
        # repo = self.git_repo_object()
        repo = Repo(self.build_dir)
        if not branch:
            branch = self.branch_2_build
        # 本地分支branch已经存在, 删除分支branch
        try:
            if branch in self.git_branches():
                self._del_branch(branch)
        except Exception as e:
            log.error(str(e))
        # 创建本地分支<branch>，pull source code
        if branch==self.git_active_branch():
            repo.git.checkout(branch, force=force)
            self.git_set_upstream(branch)
        else:
            repo.git.checkout(commit_hexsha, force=force, b=branch)
            self.git_set_upstream(branch)

    def git_fetch(self, remote_name='origin'):
        """设置origin fetch，并获取repository_url指定的git repository
        git remote add origin http://192.168.90.8/software/ifaas-inst.git<repository_url>
        git fetch --progress -v origin<remote_name>
        git fetch --tags --progress http://192.168.90.8/software/ifaas-inst.git +refs/heads/*:refs/remotes/origin/* --depth=1
         git rev-parse refs/remotes/origin/master^\{commit\}"""
        bare_repo = self.git_repo_object()
        # 判断当前repository 是否有origin远程分支，没有则创建切换到origin
        if not (bare_repo.remotes and bare_repo.remote().name == remote_name):
            origin = bare_repo.create_remote(remote_name, url=self.repository_url)
            if origin.exists():
                for fetch_info in origin.fetch(progress=MyProgressPrinter()):
                    log.info("Updated {} to {}".format(fetch_info.ref, fetch_info.commit))
                return True
        return False
        # 切换分支master
        # bare_master = bare_repo.create_head('master',origin.refs.master)
        # bare_repo.head.set_reference(bare_master)

    def git_branches(self):
        """branches 列表"""
        branches = self.git_branch_commithexsha().keys()
        return branches

    def git_local_update_remote(self):
        """git 更新本地分支与远程同步"""
        repo = self.git_repo_object()
        repo.git.fetch(['--prune origin'.split()])
        return True

    def git_branch_commithexsha(self):
        """分支：最后一次提交sha
        删除分支，本地repo更新出现不同步
        :return 字典型"""
        repo = self.git_repo_object()
        self.git_local_update_remote()
        branch_commit={}
        references = repo.references
        for r in references:
            branch_full=r.name
            branch = branch_full.split('/')[-1]
            commithexsha=r.commit.hexsha
            # refs/remotes/origin/   refs/tags/等，只挑选refs/remotes/origin/
            if self.REMOTE not in  branch_full.split('/')[:-1]:
                continue
            # 删除本地未提交情况下的，HEAD记录
            if 'HEAD' in branch_commit.keys():
                continue
            branch_commit[branch]=commithexsha

        return branch_commit

    def git_switch_branch(self, branch):
        """git checkout remotes/origin/<branch>
        git checkout -b v1.5.2 --force remotes/origin/v1.5.2"""
        if self.git_active_branch().name == branch:
            log.info("当前激活分支即是要切换分支:{}".format(branch))
            return True
        self.git_checkout("remotes/{}/{}".format(self.REMOTE,branch), branch=branch)

    def git_clone(self):
        """git clone <self.repository_url> <self.build_dir>"""
        if not os.path.exists(self.build_dir):
            Repo.clone_from(self.repository_url, self.build_dir, progress=MyProgressPrinter())

    def git_active_branch(self):
        """本地repo当前激活分支"""
        repo = self.git_repo_object()
        return str(repo.active_branch)

    def _del_branch(self,branch):
        """删除分支<branch>，刚好是当前分支，则切换到分支master"""
        repo= self.git_repo_object()
        if branch == repo.active_branch:
            if branch != self.MASTER_BRANCH_NAME:
                log.debug("刚好是当前分支{}，则切换到分支master".format(branch))
                self.git_switch_branch(self.MASTER_BRANCH_NAME)
            else:
                log.error("当前分支{}，不能删除".format(branch))
                raise Exception("git 当前激活分支{}，不能删除".format(branch))
        repo.git.branch(D=branch)

    def git_init_fetch_checkout_hexsha(self):
        """
        根据repo url , build dir ,branch ,pull指定代码
        :return last_commit_hexsha
        """
        self.git_init()
        self.git_fetch()
        last_commit = self.git_last_commit()
        self.git_checkout(last_commit)
        return last_commit


    def git_add_all(self):
        """git add -A ."""
        repo = self.git_repo_object()
        repo.git.add(A=".")

    def git_commit(self,commit=""):
        """git commit -m  "<commit>"
        """
        repo = self.git_repo_object()
        repo.git.commit(m='"{}"'.format(commit))

    def git_set_upstream(self,branch=None):
        """git branch -u origin/<branch>"""
        repo=self.git_repo_object()
        if not branch:
            branch=self.branch_2_build
        repo.git.branch(u="{}/{}".format(self.REMOTE,branch))

    def git_push(self,branch_origin=MASTER_BRANCH_NAME):
        """git  push  --set-upstream origin masterorigin <branch_origin>"""
        repo = self.git_repo_object()
        self.git_set_upstream(branch_origin)
        repo.git.push()

    def git_pull(self):
        repo = self.git_repo_object()
        self.git_set_upstream()
        repo.git.pull()


def check_fetchcode():
    args=['http://jiangyanan:phoenix619@192.168.90.8/software/ifaas-inst.git', r"F:\a", 'master']
    last_commit_hexsha = SourceCode(*args).git_init_fetch_checkout_hexsha()
    log.info(str(last_commit_hexsha))

def check_all_new_commmit():
    # 测试可同步
    args = ['http://jiangyanan:phoenix619@192.168.90.8/software/ifaas-inst.git', r"F:\a", 'master']
    SourceCode(*args).git_local_update_remote()
    new_commits=SourceCode(*args).new_commits(cur_commit_hexsha='29e761695e267f2ef0f208c620588ac52fb4aab9')
    print(len(new_commits),new_commits)
    from git import Commit
    import datetime
    for commit in new_commits:
        # commit=Commit(commit)
        print(type(datetime.datetime.fromtimestamp(commit.committed_date)),str(datetime.datetime.fromtimestamp(commit.committed_date)))

def check_sourcecode():
    """检查测试"""
    repository_url = r"http://192.168.90.8/software/ifaas-inst.git"
    # repository_url = r"http://jiangyanan:phoenix619@192.168.90.8/software/IFaceEngine.git"
    # repository_url=r"http://chenyu:006517..yc@192.168.2.2/xst/ifaas-data"
    # repository_url=r"http://jiangyanan:phoenix619@192.168.90.8/software/ifaas-version.git"
    #
    build_dir = r"F:\a"
    # build_dir = r"F:\workspace"
    sc = SourceCode(repository_url, build_dir, "master")
    # sc.git_fetch()
    # print(sc.branch_revision_kwargs)
    # sc.git_push()
    # sc.git_set_upstream("master")
    # 拖取指定分支库
    # ret = sc.git_last_commit()
    # ret = sc.git_branches()
    # last_commit = sc.git_last_commit()
    # sc.git_checkout(last_commit)
    # ret = sc.git_local_update_remote()
    # ret = sc.git_branch_commithexsha()
    # ret = sc.git_repo_object().is_dirty()
    ret =sc.git_last_commit("xkz")
    print(ret)
if __name__ == '__main__':
    # check_build()
    # check_sourcecode()
    # check_fetchcode()
    check_all_new_commmit()
