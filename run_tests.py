#!/usr/bin/env python
"""
    Install this package with different python versions with buildout
    and run `setup.py test` for each version.
"""

import sys
import os.path
import subprocess

EGG = 'Flask-Static'
VERSIONS = ('2.5', '2.6', '2.7')

def join(*parts):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), *parts)

def main(args):
    for version in VERSIONS:
        try:
            subprocess.check_call(['python' + version, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError:
            print 'python%s not available.' % version
            continue
        env = join('env' + version)
        if not os.path.isdir(env):
            print 'Creating env' + version
            os.mkdir(env)
        cfg = os.path.join(env, 'buildout.cfg')
        if not os.path.isfile(cfg):
            print 'Writing env%s/buildout.cfg' % version
            with open(cfg, 'w') as fd:
                fd.write('''
[buildout]
parts = python
develop = ..

[python]
recipe = zc.recipe.egg
interpreter = python
eggs = 
                '''.strip() + EGG)
        buildout = os.path.join(env, 'bin', 'buildout')
        if not os.path.isfile(buildout):
            bootstrap = join('bootstrap.py')
            print 'bootstrap.py in env%s' % version
            subprocess.check_call(['python' + version, bootstrap], cwd=env)
        python = os.path.join(env, 'bin', 'python')
        if not os.path.isfile(python):
            print 'env%s/bin/buildout -N' % version
            subprocess.check_call([buildout, '-N'], cwd=env)
        setup = join('setup.py')
        print 'python%s setup.py -q test -q' % version, ' '.join(args)
        subprocess.check_call([python, setup, '-q', 'test', '-q'] + list(args))

if __name__ == '__main__':
    main(sys.argv[1:])
