import functools
import aioipfs
import asyncio
import random
from datetime import datetime

from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QToolTip
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QToolBar
from PyQt5.QtWidgets import QSizePolicy

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QSize
from PyQt5.QtCore import QBuffer
from PyQt5.QtCore import QPoint

from galacteek import ensure
from galacteek import ensureLater
from galacteek import log
from galacteek import logUser
from galacteek import AsyncSignal

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs.dag import DAGRewindException
from galacteek.dweb.render import ipfsRender
from galacteek.core import utcDatetimeIso
from galacteek.core.ipfsmarks import MultihashPyramid
from galacteek.core.profile import UserProfile
from galacteek.crypto.qrcode import IPFSQrEncoder

from galacteek.did.ipid import IPService
from galacteek.did.ipid import IPIDServiceException

from .widgets import PopupToolButton
from .widgets import URLDragAndDropProcessor
from .helpers import getMimeIcon
from .helpers import getIcon
from .helpers import getIconFromIpfs
from .helpers import runDialog
from .helpers import questionBox
from .helpers import getImageFromIpfs
from .helpers import inputTextLong
from .helpers import messageBox
from .dialogs import AddMultihashPyramidDialog

from .i18n import iRemove
from .i18n import iHelp


def iCreateRawPyramid():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Create pyramid (basic)')


def iCreateGallery():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Create image gallery')


def iOpenLatestInPyramid():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Open latest item in the pyramid')


def iEmptyPyramid():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Pyramid is empty')


def iPopItemFromPyramid():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Pop item off the pyramid')


def iRewindDAG():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Rewind DAG')


def iProfilePublishToDID():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Publish on my DID')


def iProfilePublishToDIDToolTip():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Register this pyramid as a service in the list '
        'of IP services on your DID (Decentralized Identifier)')


def iRewindDAGToolTip():
    return QCoreApplication.translate(
        'pyramidMaster',
        "Rewinding the DAG cancels the latest "
        "operation/transformation in the DAG's history")


def iCopyIpnsAddress():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Copy IPNS address to clipboard')


def iPyramidPublishCurrentClipboard():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Add current clipboard item to the pyramid'
    )


def iPyramidGenerateQr():
    return QCoreApplication.translate(
        'pyramidMaster',
        "Generate pyramid's QR code"
    )


def iPyramidGenerateIndexQr():
    return QCoreApplication.translate(
        'pyramidMaster',
        "Generate index's QR code"
    )


def iGalleryBrowse():
    return QCoreApplication.translate(
        'pyramidMaster',
        "Browse image gallery"
    )


def iGalleryBrowseIpns():
    return QCoreApplication.translate(
        'pyramidMaster',
        "Browse image gallery (IPNS)"
    )


def iGalleryChangeTitle():
    return QCoreApplication.translate(
        'pyramidMaster',
        "Change image gallery's title"
    )


class MultihashPyramidsToolBar(QToolBar):
    moved = pyqtSignal(int)
    mfsInit = pyqtSignal(UserProfile)

    def __init__(self, parent):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.app.marksLocal.pyramidConfigured.connect(self.onPyramidConfigured)
        self.app.marksLocal.pyramidNeedsPublish.connect(self.publishNeeded)
        self.app.marksLocal.pyramidChanged.connect(self.onPyramidChanged)
        self.app.marksLocal.pyramidEmpty.connect(self.onPyramidEmpty)

        self.setObjectName('toolbarPyramids')
        self.setToolTip('Hashmark pyramids toolbar')
        self.setContextMenuPolicy(Qt.PreventContextMenu)
        self.setFloatable(False)
        self.setMovable(False)
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setOrientation(Qt.Vertical)

        pyrIcon = getIcon('pyramid-blue.png')
        self.pyramidsControlButton = PopupToolButton(
            icon=pyrIcon,
            mode=QToolButton.InstantPopup
        )
        self.pyramidsControlButton.setObjectName('pyramidsController')
        self.pyramidsControlButton.menu.addAction(
            getIcon('pyramid-aqua.png'),
            iCreateRawPyramid(), self.onAddPyramidRaw)
        self.pyramidsControlButton.menu.addSeparator()
        self.pyramidsControlButton.menu.addAction(
            getMimeIcon('image/x-generic'),
            iCreateGallery(), self.onAddGallery)

        self.pyramidsControlButton.menu.addSeparator()

        self.pyramidsControlButton.menu.addAction(
            pyrIcon, iHelp(), self.pyramidHelpMessage)
        self.addWidget(self.pyramidsControlButton)
        self.addSeparator()

        self.pyramids = {}
        self.setIconSize(QSize(32, 32))

    def contextMenuEvent(self, event):
        pass

    def setLargerIcons(self):
        current = self.iconSize()
        newSize = QSize(current.width() * 2, current.height() * 2)
        self.setIconSize(newSize)

    def removePyramidAsk(self, pyramidButton, action):
        reply = questionBox(
            iRemove(),
            'Remove pyramid <b>{pyr}</b> and its IPNS key ?'.format(
                pyr=pyramidButton.pyramid.name
            )
        )
        if reply is True:
            ensure(self.removePyramid(pyramidButton, action))

    async def removePyramid(self, pyramidButton, action):
        try:
            self.app.marksLocal.pyramidDrop(pyramidButton.pyramid.path)
            self.removeAction(action)

            await self.removeIpnsKey(pyramidButton.pyramid.ipnsKey)
            await pyramidButton.stop()
            await pyramidButton.cleanup()

            if pyramidButton.pyramid.path in self.pyramids:
                del self.pyramids[pyramidButton.pyramid.path]

            del pyramidButton
        except:
            log.debug('Pyramid remove failed')

    def pyramidHelpMessage(self):
        self.app.manuals.browseManualPage(
            'pyramids.html', fragment='multihash-pyramids')

    def onPyramidChanged(self, pyramidPath):
        if pyramidPath in self.pyramids:
            self.pyramids[pyramidPath].changed.emit()

    def onPyramidEmpty(self, pyramidPath):
        if pyramidPath in self.pyramids:
            self.pyramids[pyramidPath].emptyNow.emit()

    def onPyramidConfigured(self, pyramidPath):
        if pyramidPath in self.pyramids:
            # Already configured ?
            return

        pyramid = self.app.marksLocal.pyramidGet(pyramidPath)

        if pyramid is None:
            return

        if pyramid.type == MultihashPyramid.TYPE_STANDARD:
            button = MultihashPyramidToolButton(pyramid, parent=self)

        elif pyramid.type == MultihashPyramid.TYPE_GALLERY:
            button = GalleryPyramidController(pyramid, parent=self)
        else:
            # TODO
            return

        action = self.addWidget(button)
        button.deleteRequest.connect(functools.partial(
            self.removePyramidAsk, button, action))

        if pyramid.icon:
            ensure(self.fetchIcon(button, pyramid.icon))
        else:
            button.setIcon(getMimeIcon('unknown'))

        self.pyramids[pyramidPath] = button

    def publishNeeded(self, pyramidPath, mark):
        if pyramidPath in self.pyramids:
            pyramidMaster = self.pyramids[pyramidPath]
            ensure(pyramidMaster.needsPublish.emit(mark, True))

    @ipfsOp
    async def fetchIcon(self, ipfsop, button, iconPath):
        icon = await getIconFromIpfs(ipfsop, iconPath)
        if icon:
            button.setIcon(icon)
        else:
            button.setIcon(getMimeIcon('unknown'))

    @ipfsOp
    async def removeIpnsKey(self, ipfsop, ipnsKeyId):
        """
        Remove the IPNS key associated with a pyramid (called on remove)
        """
        try:
            key = await ipfsop.keyFindById(ipnsKeyId)
        except aioipfs.APIError:
            # log here
            pass
        else:
            if key:
                log.info('Removing IPNS key: {}'.format(key))
                await ipfsop.keysRemove(key['Name'])

    def onAddPyramidRaw(self):
        runDialog(AddMultihashPyramidDialog, self.app.marksLocal,
                  MultihashPyramid.TYPE_STANDARD,
                  title='New multihash pyramid',
                  parent=self)

    def onAddGallery(self):
        runDialog(AddMultihashPyramidDialog, self.app.marksLocal,
                  MultihashPyramid.TYPE_GALLERY,
                  title='New image gallery',
                  parent=self)


class MultihashPyramidToolButton(PopupToolButton):
    deleteRequest = pyqtSignal()
    changed = pyqtSignal()
    emptyNow = pyqtSignal()

    def __init__(self, pyramid, icon=None, parent=None):
        super(MultihashPyramidToolButton, self).__init__(
            mode=QToolButton.InstantPopup, parent=parent)
        self.app = QApplication.instance()

        if icon:
            self.setIcon(icon)

        self.active = True
        self._publishInProgress = False
        self._pyramid = pyramid
        self._pyramidion = None
        self._publishedLast = None
        self._publishFailedCount = 0
        self._pyrToolTip = None

        self.setAcceptDrops(True)
        self.setObjectName('pyramidMaster')

        self.clipboardItem = None
        self.app.clipTracker.currentItemChanged.connect(
            self.onClipboardItemChange)

        self.changed.connect(self.onPyrChange)
        self.emptyNow.connect(self.onPyrEmpty)

        self.needsPublish = AsyncSignal(dict, bool)
        self.needsPublish.connectTo(self.pyramidNeedsPublish)

        self.ipfsObjectDropped.connect(self.onObjectDropped)
        self.clicked.connect(self.onOpenLatest)
        self.updateToolTip()

        self.openLatestAction = QAction(getIcon('pyramid-aqua.png'),
                                        iOpenLatestInPyramid(),
                                        self,
                                        triggered=self.onOpenLatest)
        self.openLatestAction.setEnabled(False)

        self.publishCurrentClipAction = QAction(
            getIcon('clipboard.png'),
            iPyramidPublishCurrentClipboard(),
            self,
            triggered=self.onPublishClipboardItem
        )
        self.publishCurrentClipAction.setEnabled(False)

        self.popItemAction = QAction(getIcon('pyramid-stack.png'),
                                     iPopItemFromPyramid(),
                                     self,
                                     triggered=self.onPopItem)
        self.popItemAction.setEnabled(False)

        self.copyIpnsAction = QAction(getIcon('clipboard.png'),
                                      iCopyIpnsAddress(),
                                      self,
                                      triggered=self.onCopyIpns)
        self.generateQrAction = QAction(getIcon('ipfs-qrcode.png'),
                                        iPyramidGenerateQr(),
                                        self,
                                        triggered=self.onGenerateQrCode)
        self.deleteAction = QAction(getIcon('cancel.png'),
                                    iRemove(),
                                    self,
                                    triggered=self.onDeletePyramid)

        self.didPublishAction = QAction(getIcon('ipservice.png'),
                                        iProfilePublishToDID(),
                                        self,
                                        triggered=self.onPublishToDID)
        self.didPublishAction.setToolTip(iProfilePublishToDIDToolTip())

        self.createExtraActions()
        self.buildMenu()
        self.resetStyleSheet()
        ensure(self.initialize())
        self.watcherTask = self.app.task(self.publishWatcherTask)

    @property
    def pyramid(self):
        return self._pyramid

    @property
    def ipnsKeyPath(self):
        if self.pyramid.ipnsKey:
            return IPFSPath(joinIpns(self.pyramid.ipnsKey))

    @property
    def indexIpnsPath(self):
        return self.ipnsKeyPath.child('index.html')

    @property
    def pyramidion(self):
        return self._pyramidion

    @pyramidion.setter
    def pyramidion(self, capStone):
        self._pyramidion = capStone

        self.openLatestAction.setEnabled(capStone is not None)
        self.popItemAction.setEnabled(capStone is not None)

        self.debug('Pyramidion changed: {top}'.format(
            top=capStone if capStone else 'empty'))

    @property
    def publishInProgress(self):
        return self._publishInProgress

    @property
    def publishedLast(self):
        return self._publishedLast

    @publishInProgress.setter
    def publishInProgress(self, value):
        if isinstance(value, bool):
            self._publishInProgress = value
            if value is True:
                self.setStyleSheet('''
                    QToolButton {
                        background-color: #B7CDC2;
                    }
                ''')
            else:
                self.app.loop.call_later(2, self.resetStyleSheet)

    @property
    def pyrToolTip(self):
        return self._pyrToolTip

    def debug(self, msg):
        logUser.debug('{pyramid}: {msg}'.format(
            pyramid=self.pyramid.path,
            msg=msg
        ))

    def info(self, msg):
        logUser.info('{pyramid}: {msg}'.format(
            pyramid=self.pyramid.path,
            msg=msg
        ))

    async def cleanup(self):
        pass

    async def stop(self):
        if self.watcherTask:
            try:
                self.watcherTask.cancel()
            except BaseException:
                self.debug('Could not cancel watcher task')

    async def initialize(self):
        mark = self.app.marksLocal.pyramidGetLatestHashmark(self.pyramid.path)
        if mark:
            self.pyramidion = mark

    def createExtraActions(self):
        pass

    def buildMenu(self):
        self.menu.addAction(self.openLatestAction)
        self.menu.addSeparator()
        self.menu.addAction(self.publishCurrentClipAction)
        self.menu.addSeparator()
        self.menu.addAction(self.popItemAction)
        self.menu.addAction(self.copyIpnsAction)
        self.menu.addAction(self.generateQrAction)
        self.menu.addSeparator()
        self.menu.addAction(self.didPublishAction)
        self.menu.addSeparator()
        self.menu.addAction(self.deleteAction)

    def dragEnterEvent(self, event):
        URLDragAndDropProcessor.dragEnterEvent(self, event)

        if self.pyrToolTip:
            self.flashToolTip(self.pyrToolTip)
        else:
            self.flashToolTip('Pyramid: {path}'.format(path=self.pyramid.path))

        self.setStyleSheet('''
            QToolButton {
                background-color: #EB2121;
            }
        ''')

    def dropEvent(self, event):
        URLDragAndDropProcessor.dropEvent(self, event)
        self.resetStyleSheet()

    def dragLeaveEvent(self, event):
        self.resetStyleSheet()

    def resetStyleSheet(self):
        self.setStyleSheet('''
            QToolButton::hover {
                background-color: #4a9ea1;
            }

            QToolButton::pressed {
                background-color: #eec146;
            }
        ''')

    def flashToolTip(self, message):
        QToolTip.showText(self.mapToGlobal(QPoint(0, 0)), message)

    def updateToolTip(self):
        self._pyrToolTip = '''
            <p>
                <img width='64' height='64'
                    src=':/share/icons/pyramid-hierarchy.png'/>
            </p>
            <p>
                Multihash pyramid: <b>{path}</b>
                ({itemscount} item(s) in the stack)
            </p>
            <p>Description: {descr}</p>
            <p>IPNS key: <b>{ipns}</b></p>

            <p>
                <img width='16' height='16'
                    src=':/share/icons/pyramid-stack.png'/>
                Latest (pyramidion): <b>{latest}</b>
            </p>
        '''.format(
            path=self.pyramid.path,
            descr=self.pyramid.description,
            ipns=self.pyramid.ipnsKey,
            itemscount=self.pyramid.marksCount,
            latest=self.pyramid.latest if self.pyramid.latest else
            iEmptyPyramid()
        )
        self.setToolTip(self.pyrToolTip)

    def onDeletePyramid(self):
        self.deleteRequest.emit()

    def onPublishToDID(self):
        if questionBox('Publish', 'Publish to your DID ?'):
            ensure(self.didPublishService())

    def onPyrChange(self):
        self.updateToolTip()

    def onPyrEmpty(self):
        self.pyramidion = None
        ensure(self.publishEmptyObject())

    def onGenerateQrCode(self):
        if self.ipnsKeyPath:
            qrName = 'ipfsqr.{}.png'.format(self.pyramid.ipnsKey)
            ensure(self.generateQrCode(qrName, self.ipnsKeyPath))

    def onObjectDropped(self, ipfsPath):
        self.app.marksLocal.pyramidAdd(self.pyramid.path, str(ipfsPath))
        self.updateToolTip()
        self.app.systemTrayMessage(
            'Pyramids',
            'Pyramid {pyr}: registered new hashmark: {path}'.format(
                pyr=self.pyramid.path, path=str(ipfsPath)))

    def sysTray(self, message):
        self.app.systemTrayMessage(
            'Pyramids',
            'Pyramid {path}: {msg}'.format(
                path=self.pyramid.path, msg=message))

    def onPopItem(self):
        res = self.app.marksLocal.pyramidPop(self.pyramid.path)
        if res is True:
            self.sysTray('Item popped')

            if self.pyramid.empty:
                self.sysTray('Pyramid is empty now!')

    def onOpenLatest(self):
        """ Open latest object """
        if not isinstance(self.pyramid.latest, str) or not self.pyramidion:
            return

        objPath = IPFSPath(self.pyramid.latest, autoCidConv=True)
        if objPath.valid:
            ensure(self.app.resourceOpener.open(
                objPath, minWebProfile='ipfs'))

    def onClipboardItemChange(self, clipItem):
        self.clipboardItem = clipItem
        self.publishCurrentClipAction.setEnabled(True)

    def onPublishClipboardItem(self):
        if self.clipboardItem:
            reply = questionBox(
                'Publish',
                'Publish clipboard item (<b>{0}</b>) to this pyramid ?'.format(
                    str(self.clipboardItem.path))
            )
            if reply is True:
                self.app.marksLocal.pyramidAdd(
                    self.pyramid.path, str(self.clipboardItem.path)
                )

    def onCopyIpns(self):
        self.app.setClipboardText(joinIpns(self.pyramid.ipnsKey))

    @ipfsOp
    async def generateQrCode(self, ipfsop, qrName, *paths):
        encoder = IPFSQrEncoder()

        for path in paths:
            encoder.add(str(path))

        imgPath = self.app.tempDir.filePath(qrName)

        try:
            image = await encoder.encodeAll(loop=self.app.loop,
                                            executor=self.app.executor)
            image.save(imgPath)
        except:
            logUser.info('QR: encoding error ..')
            return
        else:
            logUser.info('QR: encoding successfull!')

        if ipfsop.ctx.currentProfile:
            await ipfsop.ctx.currentProfile.qrImageEncoded.emit(
                False, imgPath)

    @ipfsOp
    async def publishObject(self, ipfsop, objPath):
        return await ipfsop.publish(
            objPath,
            key=self.pyramid.ipnsKey,
            lifetime=self.pyramid.ipnsLifetime,
            cache='always',
            cacheOrigin='pyramids',
            timeout=self.app.settingsMgr.defaultIpnsTimeout
        )

    @ipfsOp
    async def publishEmptyObject(self, ipfsop):
        try:
            if ipfsop.ctx.softIdent:
                await self.publishObject(
                    ipfsop.ctx.softIdent['Hash']
                )
        except:
            pass

    @ipfsOp
    async def publish(self, ipfsop, latestMark, notify=True):
        try:
            if latestMark.path is None:
                return False

            ipfsPath = IPFSPath(latestMark.path, autoCidConv=True)
            if not ipfsPath.valid:
                self.debug('Invalid path! Cannot publish')
                return False

            self.debug('publishing mark {mark} (obj: {obj}) to {ipns}'.format(
                mark=latestMark.path,
                obj=ipfsPath.objPath,
                ipns=self.pyramid.ipnsKey
            ))

            self.publishInProgress = True

            result = await self.publishObject(
                ipfsPath.objPath
            )
        except aioipfs.APIError as err:
            self.publishInProgress = False
            self.debug('Publish error: {msg}'.format(msg=err.message))
            return False
        except Exception:
            self.publishInProgress = False
            self.debug('Unknown exception while publishing')
            return False
        else:
            self.publishInProgress = False

            if result:
                # Publish successfull
                self._publishedLast = datetime.now()

                if notify is True:
                    self.sysTray('Pyramid was published!')

                return True
            else:
                self._publishFailedCount += 1
                self.info('Publish failed: ({count} error(s))'.format(
                    count=self._publishFailedCount))
                return False

    @ipfsOp
    async def didPublishService(self, ipfsop):
        profile = ipfsop.ctx.currentProfile

        ipid = await profile.userInfo.ipIdentifier()

        try:
            await ipid.addServiceRaw({
                'id': ipid.didUrl(
                    path='/pyramids/{}'.format(
                        self.pyramid.name
                    )
                ),
                'type': IPService.SRV_TYPE_GENERICPYRAMID,
                'description': 'Generic pyramid: {}'.format(
                    self.pyramid.name
                ),
                'serviceEndpoint': self.indexIpnsPath.ipfsUrl
            })
        except IPIDServiceException as err:
            messageBox('IP Service error: {}'.format(str(err)))

    async def pyramidNeedsPublish(self, mark, notify):
        """
        We need to publish! Unless there's already a publish
        in progress, ensure an update right away
        """

        self.pyramidion = mark

        if self.publishInProgress is False:
            await self.publish(self.pyramidion, notify)

    async def publishWatcherTask(self):
        # Depending on the lifetime of the records we publish, decide upon
        # a maximum time for us not to trigger a republish
        #
        # We sorta anticipate the record expiring
        # We be nice to the network

        if self.pyramid.ipnsLifetime == '96h':
            unpublishedMax = 84 * 3600
        elif self.pyramid.ipnsLifetime == '48h':
            unpublishedMax = 42 * 3600
        elif self.pyramid.ipnsLifetime == '24h':
            unpublishedMax = 18 * 3600
        elif self.pyramid.ipnsLifetime == '12h':
            unpublishedMax = 10 * 3600
        else:
            unpublishedMax = None

        while self.active:
            await asyncio.sleep(20)

            if self.pyramidion:
                if self.publishedLast is None:
                    # Publish on startup after random delay
                    rand = random.Random()
                    delay = rand.randint(1, 10)

                    ensureLater(
                        delay,
                        self.needsPublish.emit, self.pyramidion,
                        False
                    )

                if isinstance(self.publishedLast, datetime):
                    delta = datetime.now() - self.publishedLast

                    if unpublishedMax and delta.seconds > unpublishedMax:
                        await self.needsPublish.emit(self.pyramidion, True)


class EDAGBuildingPyramidController(MultihashPyramidToolButton):
    """
    A type of pyramid that works on a EDAG, like the gallery generator
    """

    edagClass = EvolvingDAG

    def onObjectDropped(self, ipfsPath):
        pass

    def buildMenu(self):
        pass

    def createExtraActions(self):
        self.rewindDagAction = QAction(getIcon('ipld.png'),
                                       iRewindDAG(),
                                       self,
                                       triggered=self.onRewindEDAG)
        self.rewindDagAction.setToolTip(iRewindDAGToolTip())

    def onRewindEDAG(self):
        ensure(self.rewindEDAG())

    async def rewindEDAG(self):
        """
        Rewind the EDAG one iteration.

        Pop a hashmark off the pyramid, and rewind the EDAG.

        TODO: improve the EDAG rewind API so that we can know
        which object we're moving away from
        """
        try:
            self.app.marksLocal.pyramidPop(self.pyramid.path)
            await self.edag.rewind()
        except DAGRewindException:
            self.info('Cannot rewind DAG (no DAG history)')
        else:
            self.info('DAG rewind successfull')

    @ipfsOp
    async def cleanup(self, ipfsop):
        """
        Remove the EDAG's metadata file.
        We should probably also unpin the latest EDAG's object
        """
        await super().cleanup()
        await ipfsop.filesRm(self.edagMetaPath)

    async def stop(self):
        await super().stop()

    @ipfsOp
    async def initialize(self, ipfsop):
        profile = ipfsop.ctx.currentProfile
        self.edagMetaPath = profile.edagPyramidMetadataPath(self.pyramid.uuid)
        await self.initDag()

    @ipfsOp
    async def initDag(self, ipfsop):
        self.debug('Loading EDAG from MFS metadata: {}'.format(
            self.edagMetaPath))

        self.edag = self.edagClass(self.edagMetaPath)
        ensure(self.edag.load())
        await self.edag.loaded

        await self.initDagExtra(self.edag)

        self.edag.dagCidChanged.connect(self.onPyramidDagCidChanged)

        mark = self.app.marksLocal.pyramidGetLatestHashmark(self.pyramid.path)
        if mark:
            self.pyramidion = mark

    @ipfsOp
    async def initDagExtra(self, ipfsop, edag):
        pass

    def onPyramidDagCidChanged(self, cidStr):
        self.debug("Pyramid's DAG moving to CID: {}".format(cidStr))

        path = IPFSPath(cidStr)

        if path.valid:
            self.app.marksLocal.pyramidAdd(self.pyramid.path, str(path))


class GalleryDAG(EvolvingDAG):
    def updateDagSchema(self, root):
        changed = False
        if 'images' not in root:
            root['images'] = []
            changed = True

        if 'metadata' not in root:
            root['metadata'] = {
                'author': None,
                'title': 'Image gallery',
                'creationdate': utcDatetimeIso()
            }
            changed = True

        return changed


class GalleryPyramidController(EDAGBuildingPyramidController):
    edagClass = GalleryDAG

    def __init__(self, *args, **kw):
        super(GalleryPyramidController, self).__init__(
            *args, **kw)

        self.fileDropped.connect(self.onFileDropped)

    @property
    def indexPath(self):
        return IPFSPath(self.pyramid.latest, autoCidConv=True).child(
            'index.html')

    def onFileDropped(self, url):
        ensure(self.dropEventLocalFile(url))

    @ipfsOp
    async def dropEventLocalFile(self, ipfsop, url):
        entry = await self.importDroppedFileFromUrl(url)
        if entry:
            await self.analyzeImageObject(IPFSPath(entry['Hash']))

    def onObjectDropped(self, ipfsPath):
        ensure(self.analyzeImageObject(ipfsPath))

    def createExtraActions(self):
        super().createExtraActions()
        self.browseIpnsAction = QAction(getIcon('pyramid-aqua.png'),
                                        iGalleryBrowseIpns(),
                                        self,
                                        triggered=self.onBrowseGalleryIpns)
        self.browseDirectAction = QAction(getIcon('pyramid-aqua.png'),
                                          iGalleryBrowse(),
                                          self,
                                          triggered=self.onBrowseGallery)
        self.generateIndexQrAction = QAction(
            getIcon('ipfs-qrcode.png'),
            iPyramidGenerateIndexQr(),
            self,
            triggered=self.onGenerateIndexQrCode)
        self.changeTitleAction = QAction(getIcon('pyramid-aqua.png'),
                                         iGalleryChangeTitle(),
                                         self,
                                         triggered=self.onChangeTitle)

    def buildMenu(self):
        self.menu.addAction(self.browseIpnsAction)
        self.menu.addAction(self.browseDirectAction)
        self.menu.addSeparator()
        self.menu.addAction(self.copyIpnsAction)
        self.menu.addSeparator()
        self.menu.addAction(self.changeTitleAction)
        self.menu.addSeparator()
        self.menu.addAction(self.generateIndexQrAction)
        self.menu.addAction(self.generateQrAction)
        self.menu.addSeparator()
        self.menu.addAction(self.rewindDagAction)
        self.menu.addSeparator()
        self.menu.addAction(self.deleteAction)
        self.menu.addSeparator()
        self.menu.addAction(self.didPublishAction)
        self.menu.addSeparator()
        self.menu.addAction(
            getIcon('pyramid-blue.png'), iHelp(), self.galleryHelpMessage)
        self.menu.setEnabled(False)
        self.menu.setToolTipsVisible(True)

    def onPublishToDID(self):
        if questionBox('Publish', 'Publish to your DID ?'):
            ensure(self.didPublishService())

    @ipfsOp
    async def didPublishService(self, ipfsop):
        profile = ipfsop.ctx.currentProfile

        ipid = await profile.userInfo.ipIdentifier()

        try:
            await ipid.addServiceRaw({
                'id': ipid.didUrl(
                    path='/galleries/{name}'.format(
                        name=self.pyramid.name
                    )
                ),
                'type': IPService.SRV_TYPE_GALLERY,
                'serviceEndpoint': self.indexIpnsPath.ipfsUrl
            })
        except IPIDServiceException as err:
            messageBox('IP Service error: {}'.format(str(err)))

    def onChangeTitle(self):
        curTitle = self.edag.root['metadata']['title']

        title = inputTextLong(
            label='Gallery title',
            text=curTitle
        )

        if title and title != curTitle:
            ensure(self.changeGalleryTitle(title))

    @ipfsOp
    async def changeGalleryTitle(self, ipfsop, title):
        async with self.edag as edag:
            edag.root['metadata']['title'] = title

    def onGenerateIndexQrCode(self):
        qrName = 'ipfsqr.pyrindex.{}.png'.format(self.pyramid.name)
        ensure(self.generateQrCode(qrName, self.indexIpnsPath))

    def onBrowseGalleryIpns(self):
        objPath = self.ipnsKeyPath.child('index.html')
        ensure(self.app.resourceOpener.open(
            objPath, minWebProfile='ipfs'))

    def onBrowseGallery(self):
        if self.pyramid.latest:
            objPath = IPFSPath(self.pyramid.latest, autoCidConv=True).child(
                'index.html')
            ensure(self.app.resourceOpener.open(
                objPath, minWebProfile='ipfs'))

    @ipfsOp
    async def initDagExtra(self, ipfsop, edag):
        if 'index.html' not in edag.root:
            entry = await ipfsRender(self.app.jinjaEnv,
                                     'imggallery/gallery.html')
            edag.root['index.html'] = self.edag.mkLink(entry)
            edag.changed.emit()

        self.menu.setEnabled(True)

    @ipfsOp
    async def analyzeImageObject(self, ipfsop, ipfsPath):
        mimeType, stat = await self.app.rscAnalyzer(ipfsPath)

        if not mimeType or not mimeType.isImage:
            self.app.messageDisplayRequest.emit(
                'This object is not an image', 'Wrong object type')
            return

        statInfo = StatInfo(stat)
        image = await getImageFromIpfs(ipfsPath)

        if not image:
            # TODO
            return

        await ipfsop.sleep()

        imgName = ipfsPath.basename if ipfsPath.subPath else None
        tEntry = None
        maxSize = QSize(128, 128)

        # Create a thumbnail
        if image.size().width() > maxSize.width() or \
                image.size().height() > maxSize.height():

            thumbnail = await self.app.loop.run_in_executor(
                self.app.executor,
                image.scaled, maxSize, Qt.KeepAspectRatio)

            buff = QBuffer(parent=self)
            buff.open(QBuffer.ReadWrite)
            thumbnail.save(buff, 'PNG')
            buff.close()

            await ipfsop.sleep()

            data = bytes(buff.buffer())

            if len(data) > 0:
                tEntry = await ipfsop.addBytes(data)

        self.edag.root['images'].append({
            'comment': None,
            'name': imgName,
            'date': utcDatetimeIso(),
            'thumbnail': self.edag.mkLink(tEntry) if tEntry else None,
            'raw': self.edag.mkLink(statInfo.cid),
            'imginfo': {
                'width': image.width(),
                'height': image.height(),
                'depth': image.depth(),
                'bitplanes': image.bitPlaneCount(),
            }
        })

        entry = await ipfsRender(self.app.jinjaEnv,
                                 'imggallery/gallery.html')
        self.edag.root['index.html'] = self.edag.mkLink(entry)
        self.edag.changed.emit()

    def updateToolTip(self):
        self._pyrToolTip = '''
            <p>
                <img width='64' height='64'
                    src=':/share/icons/mimetypes/image-x-generic.png'/>
            </p>
            <p>
                Image gallery: <b>{path}</b>
                ({itemscount} item(s) in the stack)
            </p>

            <p><b>Drag-and-drop images here</b>
            to add an image to the gallery</p>

            <p>Description: {descr}</p>
            <p>IPNS key: <b>{ipns}</b></p>

            <p>
                <img width='16' height='16'
                    src=':/share/icons/pyramid-stack.png'/>
                Latest (pyramidion): <b>{latest}</b>
            </p>
        '''.format(
            path=self.pyramid.path,
            descr=self.pyramid.description,
            ipns=self.pyramid.ipnsKey,
            itemscount=self.pyramid.marksCount,
            latest=self.pyramid.latest if self.pyramid.latest else
            iEmptyPyramid()
        )
        self.setToolTip(self.pyrToolTip)

    def galleryHelpMessage(self):
        self.app.manuals.browseManualPage(
            'pyramids.html', fragment='image-gallery')
