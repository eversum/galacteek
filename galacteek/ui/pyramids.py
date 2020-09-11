import functools
import aioipfs
import asyncio
import random
from datetime import datetime
from pathlib import Path

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
from PyQt5.QtCore import QTimer

from galacteek import ensure
from galacteek import ensureLater
from galacteek import partialEnsure
from galacteek import log
from galacteek import logUser
from galacteek import AsyncSignal

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs.cidhelpers import ipnsKeyCidV1
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs.dag import DAGRewindException
from galacteek.dweb.render import ipfsRender
from galacteek.core import utcDatetimeIso
from galacteek.core.ipfsmarks import MultihashPyramid
from galacteek.core.ipfsmarks import IPFSHashMark
from galacteek.core.profile import UserProfile
from galacteek.core.asynclib import asyncWriteFile
from galacteek.crypto.qrcode import IPFSQrEncoder
from galacteek.core.fswatcher import FileWatcher

from galacteek.did.ipid import IPService
from galacteek.did.ipid import IPIDServiceException

from .widgets import PopupToolButton
from .widgets import URLDragAndDropProcessor
from .helpers import getMimeIcon
from .helpers import getIcon
from .helpers import getIconFromIpfs
from .helpers import runDialogAsync
from .helpers import questionBoxAsync
from .helpers import getImageFromIpfs
from .helpers import inputTextLong
from .helpers import messageBox
from .helpers import qrcFileData
from .dialogs import AddMultihashPyramidDialog
from .hashmarks import addHashmarkAsync

from .i18n import iRemove
from .i18n import iHelp
from .i18n import iHashmark
from .i18n import iOpen
from .i18n import iEditObject


def iCreateRawPyramid():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Create pyramid')


def iCreateGallery():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Create image gallery')


def iCreateAutoSyncPyramid():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Create auto-sync pyramid')


def iCreateWebsiteMkdocs():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Create website (mkdocs)')


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


def iForcePyramidSync():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Force sync')


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


def iCopyIpnsAddressGw():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Copy IPNS gateway address to clipboard')


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


def iPyramidDropper():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Choose a pyramid to publish this object to'
    )


def iPyramidDropObject():
    return QCoreApplication.translate(
        'pyramidMaster',
        'Drop object to a pyramid'
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


class PyramidsDropButton(PopupToolButton):
    def __init__(self, *args, **kw):
        super(PyramidsDropButton, self).__init__(
            mode=QToolButton.InstantPopup,
            icon=getIcon('pyramid-blue.png'),
            *args, **kw
        )
        self.menu.setTitle(iPyramidDropObject())
        self.menu.setIcon(getIcon('pyramid-blue.png'))
        self.setToolTip(iPyramidDropper())


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
        self.app.marksLocal.pyramidAddedMark.connect(self.onPyramidNewMark)

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

        # Basic pyramid (manual drag-and-drop)
        self.pyramidsControlButton.menu.addAction(
            getIcon('pyramid-aqua.png'),
            iCreateRawPyramid(), self.onAddPyramidRaw)
        self.pyramidsControlButton.menu.addSeparator()

        # Auto-sync pyramid (automatically syncs files)
        self.pyramidsControlButton.menu.addAction(
            getIcon('pyramid-aqua.png'),
            iCreateAutoSyncPyramid(),
            self.onAddPyramidAutoSync)
        self.pyramidsControlButton.menu.addSeparator()

        self.pyramidsControlButton.menu.addAction(
            getMimeIcon('image/x-generic'),
            iCreateGallery(), self.onAddGallery)
        self.pyramidsControlButton.menu.addSeparator()

        self.pyramidsControlButton.menu.addAction(
            getMimeIcon('text/html'),
            iCreateWebsiteMkdocs(),
            self.onAddPyramidWebsiteMkdocs
        )
        self.pyramidsControlButton.menu.addSeparator()

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

    async def removePyramidAsk(self, pyramidButton, action):
        reply = await questionBoxAsync(
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
            await pyramidButton.didUnpublishService()

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

    def onPyramidNewMark(self, pyramidPath, mark, mtype):
        if pyramidPath in self.pyramids:
            ensure(self.pyramids[pyramidPath].markAdded.emit(
                mark, mtype))

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
        elif pyramid.type == MultihashPyramid.TYPE_AUTOSYNC:
            button = AutoSyncPyramidButton(pyramid, parent=self)
        elif pyramid.type == MultihashPyramid.TYPE_WEBSITE_MKDOCS:
            button = WebsiteMkdocsPyramidButton(pyramid, parent=self)
        else:
            # TODO
            return

        action = self.addWidget(button)
        button.deleteRequest.connect(partialEnsure(
            self.removePyramidAsk, button, action))

        if pyramid.icon:
            ensure(self.fetchIcon(button, pyramid.icon))
        else:
            button.setIcon(getMimeIcon('unknown'))

        self.pyramids[pyramidPath] = button

    def pyramidsIdsList(self):
        return self.pyramids.keys()

    def getPyrDropButtonFor(self, ipfsPath, origin=None):
        """
        Returns a tool button to choose a pyramid to drop
        an object to
        """

        button = PyramidsDropButton()

        for pyrpath in self.pyramidsIdsList():
            pyr = self.pyramids.get(pyrpath)
            if not pyr:
                continue

            # Emit ipfsObjectDropped when selected
            # Ask confirmation here ?

            if origin and origin != pyrpath:
                # Only show origin pyramid
                continue

            button.menu.addAction(
                pyr.icon(),
                pyrpath,
                functools.partial(
                    pyr.ipfsObjectDropped.emit,
                    ipfsPath
                ))

        return button

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
                log.debug('Removing IPNS key: {}'.format(key))
                await ipfsop.keysRemove(key['Name'])

    def onAddPyramidRaw(self):
        ensure(runDialogAsync(AddMultihashPyramidDialog, self.app.marksLocal,
                              MultihashPyramid.TYPE_STANDARD,
                              title='New multihash pyramid',
                              parent=self))

    def onAddGallery(self):
        ensure(runDialogAsync(AddMultihashPyramidDialog, self.app.marksLocal,
                              MultihashPyramid.TYPE_GALLERY,
                              title='New image gallery',
                              parent=self))

    def onAddPyramidAutoSync(self):
        ensure(runDialogAsync(AddMultihashPyramidDialog, self.app.marksLocal,
                              MultihashPyramid.TYPE_AUTOSYNC,
                              title='New autosync pyramid',
                              parent=self))

    def onAddPyramidWebsiteMkdocs(self):
        ensure(runDialogAsync(AddMultihashPyramidDialog, self.app.marksLocal,
                              MultihashPyramid.TYPE_WEBSITE_MKDOCS,
                              title='New website (mkdocs)',
                              parent=self))


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

        self.markAdded = AsyncSignal(IPFSHashMark, str)

        self.lock = asyncio.Lock()
        self.active = True
        self._publishInProgress = False
        self._pyramid = pyramid
        self._pyramidion = None
        self._publishedLast = None
        self._publishFailedCount = 0
        self._publishJob = None
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

        self.ipfsObjectDropped.connect(
            lambda path: ensure(self.onObjectDropped(path)))
        self.clicked.connect(self.onOpenLatest)
        self.updateToolTip()

        self.openLatestAction = QAction(getIcon('pyramid-aqua.png'),
                                        iOpenLatestInPyramid(),
                                        self,
                                        triggered=self.onOpenLatest)
        self.openLatestAction.setEnabled(False)
        self.openAction = QAction(getIcon('pyramid-aqua.png'),
                                  iOpen(),
                                  self,
                                  triggered=self.onOpen)

        self.editAction = QAction(getIcon('pyramid-aqua.png'),
                                  iEditObject(),
                                  self,
                                  triggered=self.onEdit)

        self.inputEditAction = QAction(getIcon('pyramid-aqua.png'),
                                       iEditObject(),
                                       self,
                                       triggered=self.onInputEdit)

        self.publishCurrentClipAction = QAction(
            getIcon('clipboard.png'),
            iPyramidPublishCurrentClipboard(),
            self,
            triggered=lambda *args: ensure(self.onPublishClipboardItem())
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
        self.copyIpnsGwAction = QAction(getIcon('clipboard.png'),
                                        iCopyIpnsAddressGw(),
                                        self,
                                        triggered=self.onCopyIpnsGw)

        self.generateQrAction = QAction(getIcon('ipfs-qrcode.png'),
                                        iPyramidGenerateQr(),
                                        self,
                                        triggered=self.onGenerateQrCode)
        self.deleteAction = QAction(getIcon('cancel.png'),
                                    iRemove(),
                                    self,
                                    triggered=self.onDeletePyramid)

        self.didPublishAction = QAction(
            getIcon('ipservice.png'),
            iProfilePublishToDID(),
            self,
            triggered=lambda *args: ensure(self.onPublishToDID()))

        self.didPublishAction.setToolTip(iProfilePublishToDIDToolTip())

        self.hashmarkAction = QAction(getIcon('hashmarks.png'),
                                      iHashmark(),
                                      self,
                                      triggered=self.onHashmark)

        self.createExtraActions()

        self.resetStyleSheet()
        ensure(self.initialize())

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
        self.debug('Publish in progress: {}'.format(value))

        if isinstance(value, bool):
            self._publishInProgress = value

            if value is True:
                self.chBgColor('#B7CDC2')
            else:
                self.app.loop.call_later(1, self.resetStyleSheet)

    @property
    def pyrToolTip(self):
        return self._pyrToolTip

    def chBgColor(self, color):
        self.setStyleSheet(f'background-color: {color}')

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
                await self.watcherTask.close()
            except BaseException:
                self.debug('Could not cancel watcher task')

    async def initialize(self):
        self.buildMenu()
        self.watcherTask = await self.app.scheduler.spawn(
            self.publishWatcherTask())
        mark = self.app.marksLocal.pyramidGetLatestHashmark(self.pyramid.path)
        if mark:
            self.pyramidion = mark

    def createExtraActions(self):
        pass

    def buildMenuWithActions(self, actions):
        for action in actions:
            self.menu.addAction(action)
            self.menu.addSeparator()

    def buildMenu(self):
        self.buildMenuWithActions([
            self.openAction,
            self.openLatestAction,
            self.editAction,
            self.publishCurrentClipAction,
            self.copyIpnsAction,
            self.copyIpnsGwAction,
            self.popItemAction,
            self.generateQrAction,
            self.didPublishAction,
            self.hashmarkAction,
            self.deleteAction
        ])

    def dragEnterEvent(self, event):
        URLDragAndDropProcessor.dragEnterEvent(self, event)

        if self.pyrToolTip:
            self.flashToolTip(self.pyrToolTip)
        else:
            self.flashToolTip('Pyramid: {path}'.format(path=self.pyramid.path))

        self.chBgColor('#EB2121')

        if 0:
            self.setStyleSheet('''
                QToolButton {
                    background-color: #EB2121;
                }
            ''')

    def dropEvent(self, event):
        URLDragAndDropProcessor.dropEvent(self, event)
        self.updateBgColor()

    def dragLeaveEvent(self, event):
        self.updateBgColor()

    def updateBgColor(self):
        if not self.publishInProgress:
            self.resetStyleSheet()
        else:
            self.chBgColor('#B7CDC2')

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
            <p>IPNS key (CIDv1): <b>{ipnsv1}</b></p>

            <p>
                <img width='16' height='16'
                    src=':/share/icons/pyramid-stack.png'/>
                Latest (pyramidion): <b>{latest}</b>
            </p>
        '''.format(
            path=self.pyramid.path,
            descr=self.pyramid.description,
            ipns=self.pyramid.ipnsKey,
            ipnsv1=ipnsKeyCidV1(self.pyramid.ipnsKey),
            itemscount=self.pyramid.marksCount,
            latest=self.pyramid.latest if self.pyramid.latest else
            iEmptyPyramid()
        )
        self.setToolTip(self.pyrToolTip)

    def onDeletePyramid(self):
        self.deleteRequest.emit()

    def onHashmark(self):
        ensure(addHashmarkAsync(
            str(self.ipnsKeyPath), title=self.pyramid.name,
            description=self.pyramid.description
        ))

    async def onPublishToDID(self):
        if await questionBoxAsync('Publish', 'Publish to your DID ?'):
            await self.didPublishService()

    def onPyrChange(self):
        self.updateToolTip()

    def onPyrEmpty(self):
        self.pyramidion = None
        ensure(self.publishEmptyObject())

    def onGenerateQrCode(self):
        if self.ipnsKeyPath:
            qrName = 'ipfsqr.{}.png'.format(self.pyramid.ipnsKey)
            ensure(self.generateQrCode(qrName, self.ipnsKeyPath))

    async def cancelPublishJob(self):
        if self._publishJob:
            await self._publishJob.close()
            self._publishJob = None
            await asyncio.sleep(1)

    async def onObjectDropped(self, ipfsPath):
        await self.cancelPublishJob()

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

    def onOpen(self):
        ensure(self.app.resourceOpener.open(
            self.ipnsKeyPath, minWebProfile='ipfs'))

    def onEdit(self):
        ensure(self.app.resourceOpener.open(
            self.ipnsKeyPath, minWebProfile='ipfs',
            editObject=True))

    def onInputEdit(self):
        pass

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

    async def onPublishClipboardItem(self):
        if self.clipboardItem:
            reply = await questionBoxAsync(
                'Publish',
                'Publish current clipboard item to this pyramid ?'
            )
            if reply is True:
                self.app.marksLocal.pyramidAdd(
                    self.pyramid.path, str(self.clipboardItem.path)
                )

    def onCopyIpns(self):
        self.app.setClipboardText(str(self.ipnsKeyPath))

    def onCopyIpnsGw(self):
        self.app.setClipboardText(
            'https://ipfs.io{}'.format(str(self.ipnsKeyPath)))

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
        except asyncio.CancelledError:
            self.publishInProgress = False
            self.debug('Publish was cancelled!')
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
                self._publishFailedCount = 0

                if notify is True:
                    self.sysTray('Pyramid was published!')

                return True
            else:
                self._publishFailedCount += 1
                self.info('Publish failed: ({count} error(s))'.format(
                    count=self._publishFailedCount))
                return False

    def didPyramidUrl(self, ipid):
        return ipid.didUrl(
            path='/pyramids/{}'.format(
                self.pyramid.name
            )
        )

    @ipfsOp
    async def didUnpublishService(self, ipfsop):
        profile = ipfsop.ctx.currentProfile
        ipid = await profile.userInfo.ipIdentifier()

        if ipid:
            await ipid.removeServiceById(self.didPyramidUrl(ipid))

    @ipfsOp
    async def didPublishService(self, ipfsop):
        profile = ipfsop.ctx.currentProfile

        ipid = await profile.userInfo.ipIdentifier()

        try:
            await ipid.addServiceRaw({
                'id': self.didPyramidUrl(ipid),
                'type': IPService.SRV_TYPE_GENERICPYRAMID,
                'description': 'Generic pyramid: {}'.format(
                    self.pyramid.name
                ),
                'serviceEndpoint': self.ipnsKeyPath.ipfsUrl
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
            self._publishJob = await self.app.scheduler.spawn(
                self.publish(self.pyramidion, notify))

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
            else:
                # Wait for the pyramidion
                await asyncio.sleep(10)
                continue

            await asyncio.sleep(180)


class AutoSyncPyramidButton(MultihashPyramidToolButton):
    def __init__(self, *args, **kw):
        super(AutoSyncPyramidButton, self).__init__(*args, **kw)

        self.watcher = FileWatcher()
        self.watcher.watch(self.watchedPath)
        self.watcher.pathChanged.connect(self.onPathChanged)
        self.timer = QTimer(self)
        self.timer.timeout.connect(partialEnsure(self.onTimeout))

        self.forceSyncAction = QAction(getIcon('pyramid-stack.png'),
                                       iForcePyramidSync(),
                                       self,
                                       triggered=self.onForceSync)

    def updateToolTip(self):
        self._pyrToolTip = '''
            <p>
                <img width='64' height='64'
                    src=':/share/icons/pyramid-hierarchy.png'/>
            </p>
            <p>
                Auto-sync pyramid: <b>{path}</b>
                ({itemscount} item(s) in the stack)
            </p>
            <p>
                Auto-synced file/directory path:
                <b>{watchedpath}</b>
            </p>

            <p>Description: {descr}</p>
            <p>IPNS key: <b>{ipns}</b></p>
            <p>IPNS key (CIDv1): <b>{ipnsv1}</b></p>

            <p>
                <img width='16' height='16'
                    src=':/share/icons/pyramid-stack.png'/>
                Latest (pyramidion): <b>{latest}</b>
            </p>
        '''.format(
            path=self.pyramid.path,
            descr=self.pyramid.description,
            ipns=self.pyramid.ipnsKey,
            ipnsv1=ipnsKeyCidV1(self.pyramid.ipnsKey),
            itemscount=self.pyramid.marksCount,
            watchedpath=self.watchedPath,
            latest=self.pyramid.latest if self.pyramid.latest else
            iEmptyPyramid()
        )
        self.setToolTip(self.pyrToolTip)

    def buildMenu(self):
        self.buildMenuWithActions([
            self.openAction,
            self.openLatestAction,
            self.forceSyncAction,
            self.copyIpnsAction,
            self.copyIpnsGwAction,
            self.generateQrAction,
            self.didPublishAction,
            self.hashmarkAction,
            self.deleteAction
        ])

    def onForceSync(self):
        self.timerEnrage(now=True)

    def onPathChanged(self, path):
        self.debug(f'Watched path ({self.watchedPath}) changed')
        self.timerEnrage()

    def timerEnrage(self, now=False):
        self.timer.stop()
        self.timer.start(self.delay if not now else 100)

    async def onObjectDropped(self, ipfsPath):
        messageBox('Cannot drop content on this pyramid')

    async def initialize(self):
        await super().initialize()

        if not self.pyramidion or self.startupSync:
            # First import
            self.timerEnrage(now=True)

    async def onTimeout(self):
        self.timer.stop()
        self.debug(
            f'Watched path ({self.watchedPath}): delay finished, importing')

        async with self.lock:
            await self.cancelPublishJob()

            if await self.reinject(self.watchedPath):
                self.debug(f'Watched path ({self.watchedPath}): Import OK')

    @ipfsOp
    async def reinject(self, ipfsop, path):
        """
        Reinject watched path
        """

        self.chBgColor('orange')

        if self.pyramidion and self.unpinPrevious:
            log.debug(f'Unpinning pyramidion {self.pyramidion.path}')

            if await ipfsop.unpin(self.pyramidion.path):
                log.debug(f'Unpinning pyramidion {self.pyramidion.path}: OK')

            await ipfsop.sleep()

        entry = await ipfsop.addPath(
            path,
            recursive=True,
            useFileStore=self.useFileStore,
            hidden=self.importHiddenFiles,
            ignRulesPath=self.ignoreRulesPath,
            wrap=self.useDirWrapper
        )

        self.resetStyleSheet()

        if entry:
            await ipfsop.sleep()
            path = IPFSPath(entry['Hash'], autoCidConv=True)
            self.app.marksLocal.pyramidAdd(
                self.pyramid.path, str(path), unique=True)
            return True

        return False

    @property
    def delay(self):
        return int(self.pyramid.extra.get('syncdelay', 5000))

    @property
    def useDirWrapper(self):
        return self.pyramid.extra.get('dirwrapper', False)

    @property
    def importHiddenFiles(self):
        return self.pyramid.extra.get('importhidden')

    @property
    def ignoreRulesPath(self):
        return self.pyramid.extra['ignorerulespath']

    @property
    def useFileStore(self):
        return self.pyramid.extra['usefilestore']

    @property
    def unpinPrevious(self):
        return self.pyramid.extra['unpinprevious']

    @property
    def startupSync(self):
        return self.pyramid.extra['startupsync']

    @property
    def watchedPath(self):
        return self.pyramid.extra['autosyncpath']


class ContinuousPyramid(MultihashPyramidToolButton):
    def __init__(self, *args, **kw):
        super(ContinuousPyramid, self).__init__(*args, **kw)

        self.markAdded.connectTo(self.onMarkAdded)

    async def onMarkAdded(self, mark, mtype):
        pass

    def onInputEdit(self):
        mark = self.app.marksLocal.pyramidGetLatestInputHashmark(
            self.pyramid.path)
        if mark:
            ensure(self.app.resourceOpener.open(
                mark.path, editObject=True,
                pyramidOrigin=self.pyramid.path))

    @ipfsOp
    async def pyramidInputNew(self, ipfsop, fspath):
        entry = await ipfsop.addPath(fspath, recursive=True)
        if entry:
            path = IPFSPath(entry['Hash'])
            self.app.marksLocal.pyramidAdd(
                self.pyramid.path, str(path), unique=True,
                type='inputmark')

    @ipfsOp
    async def pyramidInputNewObject(self, ipfsop, ipfsPath):
        tmpdir = self.app.tempDirCreate(self.app.tempDir.path())

        async with ipfsop.getContexted(ipfsPath, tmpdir) as get:
            if get.finaldir:
                await self. pyramidInputNew(str(get.finaldir))

    @ipfsOp
    async def pyramidOutputNew(self, ipfsop, fspath):
        entry = await ipfsop.addPath(fspath, recursive=True)
        if entry:
            path = IPFSPath(entry['Hash'])
            self.app.marksLocal.pyramidAdd(
                self.pyramid.path, str(path), unique=True,
                type='mark')


class WebsiteMkdocsPyramidButton(ContinuousPyramid):
    """
    This pyramid generates websites with the great MKDocs.
    The input objects are IPFS UnixFS directories holding
    an MKDocs website (in markdown). The output is the generated
    website in HTML generated by MKDocs.
    """

    def buildMenu(self):
        self.buildMenuWithActions([
            self.openAction,
            self.openLatestAction,
            self.inputEditAction,
            self.copyIpnsAction,
            self.copyIpnsGwAction,
            self.generateQrAction,
            self.didPublishAction,
            self.hashmarkAction,
            self.deleteAction
        ])

    async def onObjectDropped(self, ipfsPath):
        await self.cancelPublishJob()
        async with self.lock:
            await self.pyramidInputNewObject(str(ipfsPath))

    async def onMarkAdded(self, mark, mtype):
        if mtype == 'inputmark':
            await self.mkdocsProcessInput(mark.path)

    async def mkdocsRun(self, args: list, **opts):
        try:
            proc = await asyncio.create_subprocess_shell(
                ' '.join(['mkdocs'] + args),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **opts
            )
            stdout, stderr = await proc.communicate()
        except BaseException:
            return -1, None
        else:
            return proc.returncode, stdout

    @ipfsOp
    async def mkdocsProcessInput(self, ipfsop, dIpfsPath):
        self.chBgColor('orange')
        tmpdir = self.app.tempDirCreate(self.app.tempDir.path())

        async with ipfsop.getContexted(dIpfsPath, tmpdir) as get:
            code, stdout = await self.mkdocsRun(
                ['build', '-q'], cwd=str(get.finaldir))

            self.resetStyleSheet()

            if code == 0:
                outputdir = get.finaldir.joinpath('site')
                await self.pyramidOutputNew(str(outputdir))

    @ipfsOp
    async def mkdocsNew(self, ipfsop):
        tmpdir = self.app.tempDirCreate(self.app.tempDir.path())
        tmpdirp = Path(tmpdir)

        code, stdout = await self.mkdocsRun(['new', '-q', tmpdir])
        if code == 0:
            favicon = qrcFileData(':/share/icons/ipfs-favicon.ico')

            imgpath = tmpdirp.joinpath('docs/img')
            imgpath.mkdir(parents=True, exist_ok=True)
            faviconPath = imgpath.joinpath('favicon.ico')
            configPath = tmpdirp.joinpath('mkdocs.yml')

            if favicon:
                await asyncWriteFile(str(faviconPath), bytes(favicon))

            await asyncWriteFile(
                str(configPath),
                'site_name: My dwebsite',
                mode='w+t'
            )

            await self.pyramidInputNew(tmpdir)

    async def initialize(self):
        await super().initialize()

        if not self.pyramidion:
            await self.mkdocsNew()

    def updateToolTip(self):
        self._pyrToolTip = '''
            <p>
                <img width='64' height='64'
                    src=':/share/icons/mimetypes/text-html.png'/>
            </p>
            <p>
                MKDocs website pyramid: <b>{path}</b>
                ({itemscount} item(s) in the stack)
            </p>

            <p>Description: {descr}</p>
            <p>IPNS key: <b>{ipns}</b></p>
            <p>IPNS key (CIDv1): <b>{ipnsv1}</b></p>

            <p>
                <img width='16' height='16'
                    src=':/share/icons/pyramid-stack.png'/>
                Latest (pyramidion): <b>{latest}</b>
            </p>
        '''.format(
            path=self.pyramid.path,
            descr=self.pyramid.description,
            ipns=self.pyramid.ipnsKey,
            ipnsv1=ipnsKeyCidV1(self.pyramid.ipnsKey),
            itemscount=self.pyramid.marksCount,
            latest=self.pyramid.latest if self.pyramid.latest else
            iEmptyPyramid()
        )
        self.setToolTip(self.pyrToolTip)


class EDAGBuildingPyramidController(MultihashPyramidToolButton):
    """
    A type of pyramid that works on a EDAG, like the gallery generator
    """

    edagClass = EvolvingDAG

    async def onObjectDropped(self, ipfsPath):
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
        await self.cancelPublishJob()
        try:
            await self.edag.rewind()
        except DAGRewindException:
            self.info('Cannot rewind DAG (no DAG history)')
        else:
            self.info('DAG rewind successfull')

            self.app.marksLocal.pyramidPop(
                self.pyramid.path,
                emitPublish=True
            )

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
        await super().initialize()

        profile = ipfsop.ctx.currentProfile
        self.edagMetaPath = profile.edagPyramidMetadataPath(self.pyramid.uuid)
        await self.initializeDag()

    @ipfsOp
    async def initializeDag(self, ipfsop):
        self.debug('Loading EDAG from MFS metadata: {}'.format(
            self.edagMetaPath))

        self.edag = self.edagClass(self.edagMetaPath)
        ensure(self.edag.load())
        await self.edag.loaded

        await self.initializeDagExtra(self.edag)

        self.edag.dagCidChanged.connect(self.onPyramidDagCidChanged)

        mark = self.app.marksLocal.pyramidGetLatestHashmark(self.pyramid.path)
        if mark:
            self.pyramidion = mark

    @ipfsOp
    async def initializeDagExtra(self, ipfsop, edag):
        pass

    def onPyramidDagCidChanged(self, cidStr):
        self.debug("Pyramid's DAG moving to CID: {}".format(cidStr))

        path = IPFSPath(cidStr)

        if path.valid:
            self.app.marksLocal.pyramidAdd(
                self.pyramid.path, str(path), unique=True)


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

    async def onObjectDropped(self, ipfsPath):
        await self.cancelPublishJob()
        await self.analyzeImageObject(ipfsPath)

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
        self.buildMenuWithActions([
            self.browseIpnsAction,
            self.browseDirectAction,
            self.copyIpnsAction,
            self.copyIpnsGwAction,
            self.changeTitleAction,
            self.generateIndexQrAction,
            self.generateQrAction,
            self.rewindDagAction,
            self.deleteAction,
            self.didPublishAction,
            self.hashmarkAction
        ])

        self.menu.addAction(
            getIcon('pyramid-blue.png'), iHelp(), self.galleryHelpMessage)
        self.menu.setEnabled(False)
        self.menu.setToolTipsVisible(True)

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
        await self.cancelPublishJob()
        async with self.edag as edag:
            edag.root['metadata']['title'] = title
            await self.renderGallery()

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
    async def initializeDagExtra(self, ipfsop, edag):
        if 'index.html' not in edag.root:
            entry = await ipfsRender(self.app.jinjaEnv,
                                     'imggallery/gallery-dag.html',
                                     dag=edag.root)
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

        await self.renderGallery()
        self.edag.changed.emit()

    async def renderGallery(self):
        entry = await ipfsRender(self.app.jinjaEnv,
                                 'imggallery/gallery-dag.html',
                                 dag=self.edag.root)
        self.edag.root['index.html'] = self.edag.mkLink(entry)

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
            <p>IPNS key (CIDv1): <b>{ipnsv1}</b></p>

            <p>
                <img width='16' height='16'
                    src=':/share/icons/pyramid-stack.png'/>
                Latest (pyramidion): <b>{latest}</b>
            </p>
        '''.format(
            path=self.pyramid.path,
            descr=self.pyramid.description,
            ipns=self.pyramid.ipnsKey,
            ipnsv1=ipnsKeyCidV1(self.pyramid.ipnsKey),
            itemscount=self.pyramid.marksCount,
            latest=self.pyramid.latest if self.pyramid.latest else
            iEmptyPyramid()
        )
        self.setToolTip(self.pyrToolTip)

    def galleryHelpMessage(self):
        self.app.manuals.browseManualPage(
            'pyramids.html', fragment='image-gallery')
