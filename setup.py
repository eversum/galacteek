import os
import os.path
import re
import sys
import codecs
import subprocess
import glob
import shutil

from setuptools import setup, find_packages, Command
from distutils.command.build import build

PY_VER = sys.version_info

if PY_VER >= (3, 6):
    pass
else:
    print('You need python3.6 or newer')
    print('Your python version is {0}'.format(PY_VER))
    raise RuntimeError('Invalid python version')

with codecs.open(os.path.join(os.path.abspath(os.path.dirname(
        __file__)), 'galacteek', '__init__.py'), 'r', 'latin1') as fp:
    try:
        version = re.findall(r"^__version__ = '([^']+)'\r?$",
                             fp.read(), re.M)[0]
    except IndexError:
        raise RuntimeError('Unable to determine version.')

def run(*args):
    p = subprocess.Popen(*args, stdout=subprocess.PIPE)
    stdout, err = p.communicate()
    return stdout

class build_docs(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        from sphinx import build_main
        build_main([sys.argv[0], '-b', 'html',
            'galacteek/docs/manual/en',
            'galacteek/docs/manual/en/html'])

class build_ui(Command):
    user_options = [
        ("uiforms=", None, "UI forms list to build, separated by ','"),
    ]

    def initialize_options(self):
        self.uiforms = None

    def finalize_options(self):
        pass

    def run(self):
        uifiles = []
        uidir = 'galacteek/ui'
        dstdir = uidir

        if self.uiforms:
            uifiles = [ os.path.join(uidir, '{0}.ui'.format(form)) for form
                    in self.uiforms.split(',') ]
        else:
            uifiles = glob.iglob('{}/*.ui'.format(uidir))

        for uifile in uifiles:
            print('* Building UI form:', uifile)
            base = os.path.basename(uifile).replace('.ui', '')
            out = 'ui_{}.py'.format(base)

            run(['pyuic5', '--from-imports',
                uifile,
                '-o',
                os.path.join(uidir, out)
                ])

        run(['pylupdate5', '-verbose', 'galacteek.pro'])

        trdir = './share/translations'
        lrelease = shutil.which('lrelease-qt5')

        if not lrelease:
            lrelease = shutil.which('lrelease')

        for lang in ['en', 'fr']:
            if lrelease:
                run([lrelease,
                    os.path.join(trdir, 'galacteek_{}.ts'.format(lang)),
                    '-qm',
                    os.path.join(trdir, 'galacteek_{}.qm'.format(lang)),
                    ])
            else:
                print('lrelease was not found, cannot build translation files')

        run(['pyrcc5', os.path.join(uidir, 'galacteek.qrc'), '-o',
            os.path.join(uidir, 'galacteek_rc.py')])

class _build(build):
    sub_commands = [('build_ui', None)] + build.sub_commands

with open('README.rst', 'r') as fh:
    long_description = fh.read()

deps_links = []
install_reqs = []
with open('requirements.txt') as f:
    lines = f.read().splitlines()
    for line in lines:
        if line.startswith('-e'):
            link = line.split().pop()
            deps_links.append(link)
        else:
            install_reqs.append(line)

setup(
    name='galacteek',
    version=version,
    license='GPL3',
    author='David Ferlier',
    author_email='galacteek@protonmail.com',
    url='https://github.com/eversum/galacteek',
    description='Distributed web browser',
    long_description=long_description,
    include_package_data=True,
    cmdclass={'build': _build, 'build_ui': build_ui, 'build_docs': build_docs},
    packages=[
        'galacteek',
        'galacteek.docs',
        'galacteek.docs.manual',
        'galacteek.core',
        'galacteek.core.models',
        'galacteek.crypto',
        'galacteek.ipfs',
        'galacteek.ipfs.pubsub',
        'galacteek.ipfs.pb',
        'galacteek.ipfs.p2pservices',
        'galacteek.hashmarks',
        'galacteek.hashmarks.default',
        'galacteek.templates',
        'galacteek.dweb',
        'galacteek.ui',
        'galacteek.ui.orbital'
    ],
    install_requires=install_reqs,
    dependency_links=deps_links,
    package_data={
        'galacteek': [
             'docs/manual/en/html/*.html',
             'docs/manual/en/html/_images/*',
             'docs/manual/en/html/_static/*',
            'templates/*.html',
            'templates/usersite/*.html',
            'templates/usersite/assets/*',
            'templates/usersite/assets/css/*',
            'templates/usersite/macros/*',
            'hashmarks/default/*.json'
        ]
    },
    entry_points={
        'gui_scripts': [
            'galacteek = galacteek.guientrypoint:start',
        ]
    },
    extras_require={
        'docs': [
            'sphinx>=1.7.0'
        ]
    },
    classifiers=[
        'Environment :: X11 Applications :: Qt',
        'Framework :: AsyncIO',
        'Topic :: Desktop Environment :: File Managers',
        'Topic :: Internet :: WWW/HTTP :: Browsers',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Topic :: System :: Filesystems',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7'
    ],
    keywords=[
        'asyncio',
        'aiohttp',
        'ipfs'
    ]
)
