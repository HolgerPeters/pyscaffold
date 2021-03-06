# -*- coding: utf-8 -*-

"""Unit tests of everything related to retrieving the version

There are four tree states we want to check:
 SA: sitting on the 1.0 tag
 SB: dirtying the tree after 1.0
 SC: a commit after a tag, clean tree
 SD: a commit after a tag, dirty tree

Then we're interested in 5 kinds of trees:
 TA: source tree (with .git)
 TB: source tree without .git (should get 'unknown')
 TC: source tree without .git unpacked into prefixdir
 TD: git-archive tarball
 TE: unpacked sdist tarball

In three runtime situations:
 RA1: setup.py --version
 RA2: ...path/to/setup.py --version (from outside the source tree)
 RB: setup.py sdist/bdist/bdist_wheel; pip install dist; rundemo --version

We can only detect dirty files in real git trees, so we don't examine
SB for TB/TC/TD/TE, or RB.
"""

from __future__ import absolute_import, division, print_function

import inspect
import os
import re
import shutil
import sys
from contextlib import contextmanager
from shutil import copyfile, rmtree

import pytest
from pyscaffold import shell
from pyscaffold.repo import add_tag
from pyscaffold.runner import main as putup
from pyscaffold.shell import git
from pyscaffold.utils import chdir

from .fixtures import tmpdir  # noqa

__author__ = "Florian Wilhelm"
__copyright__ = "Blue Yonder"
__license__ = "new BSD"

__location__ = os.path.join(os.getcwd(), os.path.dirname(
    inspect.getfile(inspect.currentframe())))


pip = shell.ShellCommand("pip")
setup_py = shell.ShellCommand("python setup.py")
demoapp = shell.ShellCommand("demoapp")
demoapp_data = shell.ShellCommand("demoapp_data")
untar = shell.ShellCommand("tar xvfzk")


def is_inside_venv():
    return hasattr(sys, 'real_prefix')


def create_demoapp(data=False):
    if data:
        demoapp = 'demoapp_data'
    else:
        demoapp = 'demoapp'

    putup([demoapp])
    with chdir(demoapp):
        demoapp_src_dir = os.path.join(__location__, demoapp)
        demoapp_dst_dir = os.path.join(os.getcwd(), demoapp)
        copyfile(os.path.join(demoapp_src_dir, 'runner.py'),
                 os.path.join(demoapp_dst_dir, 'runner.py'))
        git('add', os.path.join(demoapp_dst_dir, 'runner.py'))
        demoapp_dst_dir = os.getcwd()
        copyfile(os.path.join(demoapp_src_dir, 'setup.cfg'),
                 os.path.join(demoapp_dst_dir, 'setup.cfg'))
        git('add', os.path.join(demoapp_dst_dir, 'setup.cfg'))
        if data:
            data_src_dir = os.path.join(demoapp_src_dir, 'data')
            data_dst_dir = os.path.join(os.getcwd(), demoapp, 'data')
            os.mkdir(data_dst_dir)
            copyfile(os.path.join(data_src_dir, 'hello_world.txt'),
                     os.path.join(data_dst_dir, 'hello_world.txt'))
            git('add', os.path.join(data_dst_dir, 'hello_world.txt'))
        git('commit', '-m', 'Added basic progamme logic')


def build_demoapp(dist, path=None, demoapp='demoapp'):
    if path is None:
        path = os.getcwd()
    path = os.path.join(path, demoapp)
    with chdir(path):
        if dist == 'git_archive':
            os.mkdir('dist')
            filename = os.path.join('dist', '{}.tar.gz'.format(demoapp))
            git('archive', '--format', 'tar.gz', '--output', filename,
                '--prefix', '{}_unpacked/'.format(demoapp), 'HEAD')
        else:
            setup_py(dist)


@contextmanager
def installed_demoapp(dist=None, path=None, demoapp='demoapp'):
    if path is None:
        path = os.getcwd()
    path = os.path.join(path, demoapp, "dist", "{}*".format(demoapp))
    if dist == 'bdist':
        with chdir('/'):
            output = untar(path)
        install_dirs = list()
        install_bin = None
        for line in output:
            if re.search(r".*/site-packages/{}.*?/$".format(demoapp), line):
                install_dirs.append(line)
            if re.search(r".*/bin/{}$".format(demoapp), line):
                install_bin = line
    elif dist == 'install':
        pass
    else:
        pip("install", path)
    try:
        yield
    finally:
        if dist == 'bdist':
            with chdir('/'):
                os.remove(install_bin)
                for path in install_dirs:
                    rmtree(path, ignore_errors=True)
        else:
            pip("uninstall", "-y", demoapp)


def check_version(output, exp_version, dirty=False):
    version = output.split(' ')[1]
    # for some setuptools version a directory with + is generated, sometimes _
    if dirty:
        if '+' in version:
            ver, local = version.split('+')
        else:
            ver, local = version.split('_')
        assert local.endswith('dirty')
        assert ver == exp_version
    else:
        if '+' in version:
            ver = version.split('+')
        else:
            ver = version.split('_')
        if len(ver) > 1:
            assert not ver[1].endswith('dirty')
        assert ver[0] == exp_version


def make_dirty_tree(demoapp='demoapp'):
    dirty_file = os.path.join(demoapp, 'runner.py')
    with chdir(demoapp):
        with open(dirty_file, 'a') as fh:
            fh.write("\n\ndirty_variable = 69\n")


def rm_git_tree(demoapp='demoapp'):
    git_path = os.path.join(demoapp, '.git')
    shutil.rmtree(git_path)


def test_sdist_install(tmpdir):  # noqa
    create_demoapp()
    build_demoapp('sdist')
    with installed_demoapp():
        out = next(demoapp('--version'))
        exp = "0.0.post0.dev1"
        check_version(out, exp, dirty=False)


def test_sdist_install_dirty(tmpdir):  # noqa
    create_demoapp()
    make_dirty_tree()
    build_demoapp('sdist')
    with installed_demoapp():
        out = next(demoapp('--version'))
        exp = "0.0.post0.dev1"
        check_version(out, exp, dirty=True)


def test_sdist_install_with_1_0_tag(tmpdir):  # noqa
    create_demoapp()
    add_tag('demoapp', 'v1.0', 'final release')
    build_demoapp('sdist')
    with installed_demoapp():
        out = next(demoapp('--version'))
        exp = "1.0"
        check_version(out, exp, dirty=False)


def test_sdist_install_with_1_0_tag_dirty(tmpdir):  # noqa
    create_demoapp()
    add_tag('demoapp', 'v1.0', 'final release')
    make_dirty_tree()
    build_demoapp('sdist')
    with installed_demoapp():
        out = next(demoapp('--version'))
        exp = "1.0"
        check_version(out, exp, dirty=True)


# bdist works like sdist so we only try one combination
def test_bdist_install(tmpdir):  # noqa
    create_demoapp()
    build_demoapp('bdist')
    with installed_demoapp('bdist'):
        out = next(demoapp('--version'))
        exp = "0.0.post0.dev1"
        check_version(out, exp, dirty=False)


# bdist wheel works like sdist so we only try one combination
@pytest.mark.skipif(not is_inside_venv(),  # noqa
                    reason='Needs to run in a virtualenv')
def test_bdist_wheel_install(tmpdir):
    create_demoapp()
    build_demoapp('bdist_wheel')
    with installed_demoapp():
        out = next(demoapp('--version'))
        exp = "0.0.post0.dev1"
        check_version(out, exp, dirty=False)


# git archive really only works when we sit on a tag
def test_git_archive(tmpdir):  # noqa
    create_demoapp()
    add_tag('demoapp', 'v1.0', 'final release')
    build_demoapp('git_archive')
    untar(os.path.join('demoapp', 'dist', 'demoapp.tar.gz'))
    with chdir('demoapp_unpacked'):
        out = list(setup_py('version'))[-1]
        exp = '1.0'
        check_version(out, exp, dirty=False)


def test_git_repo(tmpdir):  # noqa
    create_demoapp()
    build_demoapp('install')
    with chdir('demoapp'):
        out = list(setup_py('version'))[-1]
        exp = '0.0.post0.dev1'
        check_version(out, exp, dirty=False)


def test_git_repo_dirty(tmpdir):  # noqa
    create_demoapp()
    make_dirty_tree()
    build_demoapp('install')
    with chdir('demoapp'):
        out = list(setup_py('version'))[-1]
        exp = '0.0.post0.dev1'
        check_version(out, exp, dirty=True)


def test_git_repo_with_1_0_tag(tmpdir):  # noqa
    create_demoapp()
    add_tag('demoapp', 'v1.0', 'final release')
    build_demoapp('install')
    with chdir('demoapp'):
        out = list(setup_py('version'))[-1]
        exp = '1.0'
        check_version(out, exp, dirty=False)


def test_git_repo_with_1_0_tag_dirty(tmpdir):  # noqa
    create_demoapp()
    add_tag('demoapp', 'v1.0', 'final release')
    make_dirty_tree()
    build_demoapp('install')
    with chdir('demoapp'):
        out = list(setup_py('version'))[-1]
        exp = '1.0'
        check_version(out, exp, dirty=True)


def test_parentdir(tmpdir):  # noqa
    create_demoapp()
    add_tag('demoapp', 'v1.0', 'final release')
    build_demoapp('sdist')
    path = os.path.join("demoapp", "dist", "demoapp*")
    untar(path)
    with chdir('demoapp-1.0'):
        out = list(setup_py('version'))[-1]
        exp = '1.0'
        check_version(out, exp, dirty=False)


def test_sdist_install_with_data(tmpdir):  # noqa
    create_demoapp(data=True)
    build_demoapp('sdist', demoapp='demoapp_data')
    with installed_demoapp(demoapp='demoapp_data'):
        out = next(demoapp_data())
        exp = "Hello World"
        assert out.startswith(exp)


def test_bdist_install_with_data(tmpdir):  # noqa
    create_demoapp(data=True)
    build_demoapp('bdist', demoapp='demoapp_data')
    with installed_demoapp('bdist', demoapp='demoapp_data'):
        out = next(demoapp_data())
        exp = "Hello World"
        assert out.startswith(exp)


@pytest.mark.skipif(not is_inside_venv(),  # noqa
                    reason='Needs to run in a virtualenv')
def test_bdist_wheel_install_with_data(tmpdir):
    create_demoapp(data=True)
    build_demoapp('bdist_wheel', demoapp='demoapp_data')
    with installed_demoapp(demoapp='demoapp_data'):
        out = next(demoapp_data())
        exp = "Hello World"
        assert out.startswith(exp)


def test_setup_py_install(tmpdir):  # noqa
    create_demoapp()
    build_demoapp('install', demoapp='demoapp')
    with installed_demoapp('install', demoapp='demoapp'):
        out = next(demoapp('--version'))
        exp = "0.0.post0.dev1"
        check_version(out, exp, dirty=False)
