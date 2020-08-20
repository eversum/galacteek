import os
import os.path
import asyncio
import aioipfs

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QUrl

from galacteek import log
from galacteek import logUser
from galacteek import ensure
from galacteek import partialEnsure
from galacteek import AsyncSignal

from galacteek.did.ipid import IPService

from galacteek.dweb.page import PDFViewerPage
from galacteek.dweb.page import WebTab
from galacteek.dweb.page import DWebView

from galacteek.ipfs import megabytes
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.stat import StatInfo

from galacteek.ipfs.mimetype import MIMEType
from galacteek.ipfs.mimetype import detectMimeType
from galacteek.ipfs.mimetype import detectMimeTypeFromBuffer
from galacteek.ipfs.mimetype import mimeTypeDagUnknown

from galacteek.ipfs.cidhelpers import IPFSPath

from galacteek.core.schemes import isEnsUrl

from .dag import DAGViewer
from .textedit import TextEditorTab
from .dialogs import ResourceOpenConfirmDialog
from .helpers import getIcon
from .helpers import getMimeIcon
from .helpers import messageBox
from .helpers import runDialogAsync
from .imgview import ImageViewerTab
from .i18n import iDagViewer


def iResourceCannotOpen(path):
    return QCoreApplication.translate(
        'resourceOpener',
        '{}: cannot determine resource type or timeout occured '
        '(check connectivity)').format(
            path)


class IPFSResourceOpener(QObject):
    objectOpened = pyqtSignal(IPFSPath)

    # Emitted by the opener when we want to show a dialog for confirmation
    needUserConfirm = AsyncSignal(IPFSPath, MIMEType, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = QApplication.instance()
        self.setObjectName('resourceOpener')
        self.needUserConfirm.connectTo(self.onNeedUserConfirm)

    def openEnsUrl(self, url, pin=False):
        self.app.mainWindow.addBrowserTab(
            minProfile='web3', pinBrowsed=pin).enterUrl(url)

    @ipfsOp
    async def open(self, ipfsop, pathRef,
                   mimeType=None,
                   openingFrom=None,
                   pyramidOrigin=None,
                   minWebProfile='ipfs',
                   schemePreferred=None,
                   tryDecrypt=False,
                   fromEncrypted=False,
                   editObject=False,
                   pin=False,
                   burnAfterReading=False):
        """
        Open the resource referenced by rscPath according
        to its MIME type

        :param pathRef: IPFS object's path (can be str or IPFSPath)
        :param openingFrom str: UI component making the open request
        :param minWebProfile str: Minimum Web profile to use
        :param tryDecrypt bool: Try to decrypt the object or not
        :param editObject bool: Set Text Editor in edit mode for text files
        :param MIMEType mimeType: MIME type
        """

        ipfsPath = None
        statInfo = None

        if isinstance(pathRef, IPFSPath):
            ipfsPath = pathRef
        elif isinstance(pathRef, str):
            url = QUrl(pathRef)

            if isEnsUrl(url):
                return self.openEnsUrl(url, pin=pin)

            ipfsPath = IPFSPath(pathRef, autoCidConv=True)
        else:
            raise ValueError('Invalid input value')

        if not ipfsPath.valid:
            return False

        rscPath = ipfsPath.objPath

        if self.app.mainWindow.pinAllGlobalChecked:
            ensure(ipfsop.ctx.pinner.queue(rscPath, False,
                                           None,
                                           qname='default'))

        rscShortName = ipfsPath.shortRepr()

        if ipfsPath.isIpfs:
            # Try to reuse metadata from the multihash store
            rscMeta = await self.app.multihashDb.get(rscPath)
            if rscMeta:
                cachedMime = rscMeta.get('mimetype')
                cachedStat = rscMeta.get('stat')
                if cachedMime:
                    mimeType = MIMEType(cachedMime)
                if cachedStat:
                    statInfo = StatInfo(cachedStat)

        if mimeType is None:
            mimeType = await detectMimeType(rscPath)

        if mimeType and mimeType.valid:
            logUser.info('{path} ({type}): opening'.format(
                path=rscPath, type=str(mimeType)))
        else:
            logUser.info(iResourceCannotOpen(rscPath))
            return

        if mimeType == mimeTypeDagUnknown:
            indexPath = ipfsPath.child('index.html')
            stat = await ipfsop.objStat(indexPath.objPath, timeout=8)

            if stat:
                # Browse the index
                return self.app.mainWindow.addBrowserTab(
                    minProfile=minWebProfile,
                    pinBrowsed=pin).browseFsPath(
                        indexPath, schemePreferred=schemePreferred)

            # Otherwise view the DAG
            view = DAGViewer(rscPath, self.app.mainWindow)
            self.app.mainWindow.registerTab(
                view, iDagViewer(),
                current=True,
                icon=getIcon('ipld.png'),
                tooltip=rscPath
            )
            return

        if mimeType.type == 'application/octet-stream' and not fromEncrypted:
            # Try to decode it with our key if it's a small file
            if statInfo is None:
                statInfo = StatInfo(await ipfsop.objStat(rscPath, timeout=5))

            profile = ipfsop.ctx.currentProfile
            if profile and statInfo.valid and \
                    (statInfo.dataSmallerThan(megabytes(8)) or tryDecrypt):
                data = await ipfsop.catObject(ipfsPath.objPath, timeout=30)
                if not data:
                    # XXX
                    return

                decrypted = await profile.rsaAgent.decrypt(data)

                if decrypted:
                    #
                    # "Good evening, 007"
                    #
                    # Create a short-lived IPFS offline file (not announced)
                    # with the decrypted content and open it
                    #

                    logUser.info('{path}: RSA OK'.format(path=rscPath))

                    # This one won't be announced or pinned
                    entry = await ipfsop.addBytes(decrypted,
                                                  offline=True,
                                                  pin=False)
                    if not entry:
                        logUser.info(
                            '{path}: cannot import decrypted file'.format(
                                path=rscPath))
                        return

                    # Open the decrypted file
                    return ensure(self.open(entry['Hash'],
                                            fromEncrypted=True,
                                            burnAfterReading=True))
                else:
                    logUser.debug(
                        '{path}: decryption impossible'.format(path=rscPath))

        if mimeType.isText or editObject:
            tab = TextEditorTab(
                parent=self.app.mainWindow,
                editing=editObject,
                pyramidOrigin=pyramidOrigin
            )
            tab.editor.display(ipfsPath)
            self.objectOpened.emit(ipfsPath)
            return self.app.mainWindow.registerTab(
                tab,
                rscShortName,
                icon=getMimeIcon('text/x-generic'),
                tooltip=rscPath,
                current=True
            )

        if mimeType.isImage or mimeType.isAnimation:
            tab = ImageViewerTab(self.app.mainWindow)
            ensure(tab.view.showImage(rscPath))
            self.objectOpened.emit(ipfsPath)
            return self.app.mainWindow.registerTab(
                tab,
                rscShortName,
                icon=getMimeIcon('image/x-generic'),
                tooltip=rscPath,
                current=True
            )

        if mimeType.isVideo or mimeType.isAudio:
            tab = self.app.mainWindow.getMediaPlayer()
            if tab:
                tab.playFromPath(rscPath)
            return

        if mimeType == 'application/pdf' and 0:  # not usable yet
            tab = WebTab(self.app.mainWindow)
            tab.attach(
                DWebView(page=PDFViewerPage(rscPath))
            )
            self.objectOpened.emit(ipfsPath)
            return self.app.mainWindow.registerTab(
                tab,
                rscShortName,
                icon=getMimeIcon('application/pdf'),
                tooltip=rscPath,
                current=True
            )

        if mimeType.isHtml:
            self.objectOpened.emit(ipfsPath)
            return self.app.mainWindow.addBrowserTab(
                minProfile=minWebProfile,
                pinBrowsed=pin).browseFsPath(
                    ipfsPath, schemePreferred=schemePreferred)

        if mimeType.isDir:
            indexPath = ipfsPath.child('index.html')
            stat = await ipfsop.objStat(indexPath.objPath, timeout=8)

            if stat:
                self.objectOpened.emit(ipfsPath)
                return self.app.mainWindow.addBrowserTab(
                    minProfile=minWebProfile,
                    pinBrowsed=pin).browseFsPath(
                        ipfsPath, schemePreferred=schemePreferred)
            else:
                return await self.app.mainWindow.exploreIpfsPath(ipfsPath)

        if openingFrom in ['filemanager', 'qa', 'didlocal']:
            await self.needUserConfirm.emit(ipfsPath, mimeType, True)
        else:
            await self.needUserConfirm.emit(ipfsPath, mimeType, False)

    async def onNeedUserConfirm(self, ipfsPath, mimeType, secureFlag):
        await runDialogAsync(
            ResourceOpenConfirmDialog, ipfsPath, mimeType, secureFlag,
            accepted=partialEnsure(self.onOpenConfirmed, ipfsPath,
                                   mimeType))

    async def onOpenConfirmed(self, iPath, mType, dlg):
        log.debug('Open confirmed for: {0}'.format(iPath))
        await self.openWithSystemDefault(str(iPath))

    @ipfsOp
    async def openBlock(self, ipfsop, pathRef, mimeType=None):
        """
        Open the raw block referenced by pathRef

        XXX: needs improvements, this only works for images for now
        """

        ipfsPath = None

        if isinstance(pathRef, IPFSPath):
            ipfsPath = pathRef
        elif isinstance(pathRef, str):
            ipfsPath = IPFSPath(pathRef)
        else:
            raise ValueError('Invalid input value')

        if not ipfsPath.valid:
            return False

        blockStat = await ipfsop.waitFor(
            ipfsop.client.block.stat(pathRef), 5
        )

        if not blockStat or not isinstance(blockStat, dict):
            messageBox('Block is bad')

        blockSize = blockStat.get('Size')

        if blockSize > megabytes(16):
            return

        logUser.info('Block {path}: Opening'.format(path=pathRef))

        blockData = await ipfsop.client.block.get(pathRef)

        rscPath = ipfsPath.objPath
        rscShortName = rscPath
        mimeType = await detectMimeTypeFromBuffer(blockData[:1024])

        if mimeType and mimeType.valid:
            logUser.info('Block: {path} ({type}): opening'.format(
                path=rscPath, type=str(mimeType)))
        else:
            return messageBox(iResourceCannotOpen(rscPath))

        if mimeType.isImage:
            tab = ImageViewerTab(self.app.mainWindow)
            ensure(tab.view.showImage(rscPath, fromBlock=True))
            self.objectOpened.emit(ipfsPath)
            return self.app.mainWindow.registerTab(
                tab,
                rscShortName,
                icon=getMimeIcon('image/x-generic'),
                tooltip=rscPath,
                current=True
            )

    @ipfsOp
    async def openWithExternal(self, ipfsop, rscPath, progArgs):
        filePath = os.path.join(self.app.tempDir.path(),
                                os.path.basename(rscPath))

        if not os.path.exists(filePath):
            try:
                await ipfsop.client.get(rscPath,
                                        dstdir=self.app.tempDir.path())
            except aioipfs.APIError as err:
                log.debug(err.message)
                return

        if not os.path.isfile(filePath):
            # Bummer
            return

        filePathEsc = filePath.replace('"', r'\"')
        args = progArgs.replace('%f', filePathEsc)

        log.info('Object opener: executing: {}'.format(args))

        try:
            proc = await asyncio.create_subprocess_shell(
                args,
                stdout=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
        except BaseException as err:
            os.unlink(filePath)
            log.debug(str(err))
        else:
            os.unlink(filePath)

    async def openWithSystemDefault(self, rscPath):
        # Use xdg-open or open depending on the platform
        if self.app.system == 'Linux':
            await self.openWithExternal(rscPath, 'xdg-open "%f"')
        elif self.app.system == 'Darwin':
            await self.openWithExternal(rscPath, 'open "%f"')

    @ipfsOp
    async def browseIpService(self, ipfsop, serviceId, serviceCtx=None):
        """
        Browse/open an IP service registered on an IPID
        """

        log.info('Accessing IP service {}'.format(serviceId))

        pService = await ipfsop.ipidManager.getServiceById(serviceId)
        if not pService:
            return

        endpoint = pService.endpoint

        if pService.type == IPService.SRV_TYPE_ATOMFEED:
            await self.app.mainWindow.atomButton.atomFeedSubscribe(
                str(endpoint)
            )

        elif isinstance(endpoint, str):
            path = IPFSPath(endpoint, autoCidConv=True)
            await self.open(path)

    @ipfsOp
    async def openIpServiceObject(self, ipfsop, serviceId, objectId):
        log.info('Accessing IP service object {}'.format(objectId))

        pService = await ipfsop.ipidManager.getServiceById(serviceId)
        if not pService:
            log.info('Cannot find service {}'.format(serviceId))
            return

        obj = await pService.getObjectWithId(objectId)
        if obj:
            path = IPFSPath(obj['path'], autoCidConv=True)
            await self.open(path)
        else:
            log.info('Cannot find object {}'.format(objectId))
