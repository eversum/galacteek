# Galacteek, GUI startup entry point

import argparse
import sys

from PyQt5.QtCore import QProcess
from PyQt5.QtWebEngine import QtWebEngine

from galacteek import log
from galacteek import __version__
from galacteek.core import glogger
from galacteek.core.schemes import initializeSchemes

from galacteek.ui.helpers import *  # noqa
from galacteek import application
from galacteek.appsettings import *  # noqa

try:
    import aiomonitor
except ImportError:
    haveAiomonitor = False
else:
    haveAiomonitor = True


appStarter = None


class ApplicationStarter:
    def __init__(self, args):
        self.args = args

    def start(self):
        galacteekGui(self.args)

    def startProcess(self, args):
        p = QProcess()
        prog = self.args.binarypath if self.args.binarypath else args[0]
        p.setProgram(prog)
        if len(args) > 1:
            p.setArguments(args[1:])
        p.startDetached()


def galacteekGui(args):
    progName = args.binaryname if args.binaryname else sys.argv[0]

    if args.debug:
        glogger.basicConfig(level='DEBUG')
    else:
        glogger.basicConfig(level='INFO')

    # QtWebEngine init
    QtWebEngine.initialize()

    # Initialize webengine schemes before creating the application
    initializeSchemes()

    gApp = application.GalacteekApplication(
        profile=args.profile,
        debug=args.debug,
        enableOrbital=args.enableorbital,
        sslverify=False if args.nosslverify else True,
        progName=progName,
        cmdArgs=args
    )
    loop = gApp.loop
    sManager = gApp.settingsMgr

    section = CFG_SECTION_IPFSD
    if args.apiport:
        sManager.setSetting(section, CFG_KEY_APIPORT, args.apiport)
    if args.swarmport:
        sManager.setSetting(section, CFG_KEY_SWARMPORT, args.swarmport)
    if args.gatewayport:
        sManager.setSetting(section, CFG_KEY_HTTPGWPORT, args.gatewayport)

    # Monitor event loop if aiomonitor is available
    # Use the context manager so loop cleanup/close is automatic

    if args.monitor is True and haveAiomonitor:
        with aiomonitor.start_monitor(loop=loop):
            with loop:
                loop.run_forever()
    else:
        with loop:
            log.debug('Inside context manager')
            loop.run_forever()


def start():
    global appStarter
    parser = argparse.ArgumentParser()

    parser.add_argument('--version', dest='version',
                        action='store_true',
                        help='Show version number')
    parser.add_argument('--apiport', default=None,
                        help='IPFS API port number')
    parser.add_argument('--swarmport', default=None,
                        help='IPFS swarm port number')
    parser.add_argument('--gatewayport', default=None,
                        help='IPFS http gateway port number')
    parser.add_argument('--profile', default='main',
                        help='Application Profile')
    parser.add_argument('--binary-name', default=None,
                        help='Binary name', dest='binaryname')
    parser.add_argument('--binary-path', default=None,
                        help='Binary path', dest='binarypath')
    parser.add_argument(
        '--monitor',
        action='store_true',
        dest='monitor',
        help='Monitor application with aiomonitor')
    parser.add_argument(
        '--seed',
        action='store_true',
        dest='seed',
        help='Automatic AppImage seeding')
    parser.add_argument(
        '--from-appimage',
        action='store_true',
        dest='appimage',
        help='Running from an AppImage')
    parser.add_argument(
        '--from-dmg',
        action='store_true',
        dest='dmg',
        help='Running from a DMG image')
    parser.add_argument(
        '--migrate',
        action='store_true',
        dest='migrate',
        default=True,
        help='Activate automatic repository migration')
    parser.add_argument(
        '--no-release-check',
        action='store_true',
        dest='noreleasecheck',
        default=True,
        help="Don't check for new releases on PyPI")
    parser.add_argument(
        '--no-ssl-verify',
        action='store_true',
        dest='nosslverify',
        help="Don't check for SSL certificate validity (ipfs-search)")
    parser.add_argument(
        '--no-ipfsscheme-mutex',
        action='store_true',
        dest='noipfsmutexlock',
        help="Don't use Qt mutexes in the native IPFS scheme handler")
    parser.add_argument(
        '--force-goipfs-download',
        action='store_true',
        dest='forcegoipfsdl',
        help="Force go-ipfs download")
    parser.add_argument(
        '--enable-orbital',
        action='store_true',
        dest='enableorbital',
        help="Enable orbit-db connector")

    parser.add_argument('-d', action='store_true',
                        dest='debug', help='Activate debugging')
    args = parser.parse_args()

    if args.version is True:
        print(__version__)
        sys.exit()

    appStarter = ApplicationStarter(args)
    appStarter.start()
