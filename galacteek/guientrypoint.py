# Galacteek, GUI startup entry point

import asyncio
import argparse
import shutil
import subprocess
import sys
import re
from distutils.version import StrictVersion

from PyQt5.QtCore import QProcess
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import Qt

from galacteek import log
from galacteek import ensure
from galacteek import __version__
from galacteek.core import glogger
from galacteek.core.schemes import initializeSchemes

from galacteek.ipfs import distipfsfetch
from galacteek.ui.helpers import *  # noqa
from galacteek.ui.i18n import (
    iGoIpfsFetchTimeout,
    iGoIpfsNotFound,
    iGoIpfsTooOld,
    iGoIpfsFetchAsk,
    iGoIpfsFetchError,
    iGoIpfsFetchSuccess,
    iFsRepoMigrateNotFound
)
from galacteek import application
from galacteek.appsettings import *  # noqa

try:
    import aiomonitor
except ImportError:
    haveAiomonitor = False
else:
    haveAiomonitor = True


appStarter = None


def whichIpfs():
    return shutil.which('ipfs')


def ipfsVersion():
    try:
        p = subprocess.Popen(['ipfs', 'version', '-n'], stdout=subprocess.PIPE)
        out, err = p.communicate()
        version = out.decode().strip()
        version = re.sub('(-.*$)', '', version)
        return StrictVersion(version)
    except BaseException:
        return None


async def fetchGoIpfsWrapper(app, timeout=60 * 10):
    try:
        await asyncio.wait_for(fetchGoIpfsDist(app), timeout)
    except asyncio.TimeoutError:
        app.mainWindow.statusMessage(iGoIpfsFetchTimeout())
        return None
    except Exception:
        app.mainWindow.statusMessage(iGoIpfsFetchError())
        return None
    else:
        app.mainWindow.statusMessage(iGoIpfsFetchSuccess())
        return whichIpfs()


async def fetchGoIpfsDist(app):
    async for msg in distipfsfetch.distIpfsExtract(
            dstdir=app.ipfsBinLocation, software='go-ipfs',
            executable='ipfs', version='0.4.22', loop=app.loop,
            sslverify=app.sslverify):
        try:
            code, text = msg
            app.mainWindow.statusMessage(text)
        except Exception as e:
            app.debug(str(e))


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

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

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

    if sManager.isTrue(CFG_SECTION_IPFSD, CFG_KEY_ENABLED):
        fsMigratePath = shutil.which('fs-repo-migrations')
        hasFsMigrate = fsMigratePath is not None

        if hasFsMigrate is False and args.migrate is True:
            gApp.systemTrayMessage('Galacteek', iFsRepoMigrateNotFound())

        enableMigrate = hasFsMigrate is True and args.migrate is True

        # Look if we can find the ipfs executable
        ipfsPath = whichIpfs()
        minVersion = StrictVersion('0.4.7')

        if ipfsPath is None or args.forcegoipfsdl:
            if args.forcegoipfsdl:
                fetchWanted = True
            else:
                fetchWanted = questionBox('go-ipfs', iGoIpfsFetchAsk())

            def fetchFinished(fut):
                path = fut.result()
                if path is None:
                    gApp.systemTrayMessage('Galacteek',
                                           iGoIpfsFetchError())
                else:
                    gApp.startIpfsDaemon(goIpfsPath=path,
                                         migrateRepo=enableMigrate)

            if fetchWanted:
                fut = ensure(fetchGoIpfsWrapper(gApp))
                fut.add_done_callback(fetchFinished)
            else:
                gApp.systemTrayMessage('Galacteek',
                                       iGoIpfsNotFound())
        else:
            iVersion = ipfsVersion()
            if not iVersion or iVersion < minVersion:
                # warning here
                log.debug('go-ipfs version found {0} is too old'.format(
                    iVersion))
                gApp.systemTrayMessage('Galacteek',
                                       iGoIpfsTooOld())

            gApp.startIpfsDaemon(goIpfsPath=ipfsPath,
                                 migrateRepo=enableMigrate)
    else:
        ensure(gApp.updateIpfsClient())

    if args.noreleasecheck is False:
        ensure(gApp.checkReleases())

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
        help='Activate automatic repository migration')
    parser.add_argument(
        '--no-release-check',
        action='store_true',
        dest='noreleasecheck',
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
