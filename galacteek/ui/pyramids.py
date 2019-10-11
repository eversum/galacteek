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

from PyQt5.QtCore import QPoint

from galacteek import ensure
from galacteek import log
from galacteek import logUser
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs import ipfsOp
from galacteek.core.ipfsmarks import IPFSHashMark
from galacteek.core.profile import UserProfile
from galacteek.crypto.qrcode import IPFSQrEncoder

from .widgets import PopupToolButton
from .widgets import URLDragAndDropProcessor
from .helpers import getMimeIcon
from .helpers import getIcon
from .helpers import getIconFromIpfs
from .helpers import runDialog
from .helpers import questionBox
from .dialogs import AddMultihashPyramidDialog

from .i18n import iRemove


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
            'Add multihash pyramid', self.onAddPyramid)

        self.pyramidsControlButton.menu.addSeparator()

        self.pyramidsControlButton.menu.addAction(
            pyrIcon, 'Help', self.pyramidHelpMessage)
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

    def removePyramid(self, pyramidButton, action):
        reply = questionBox(
            iRemove(),
            'Remove pyramid <b>{pyr}</b> and its IPNS key ?'.format(
                pyr=pyramidButton.pyramid.name
            )
        )
        if reply is True:
            try:
                self.app.marksLocal.pyramidDrop(pyramidButton.pyramid.path)
                self.removeAction(action)
                ensure(self.removeIpnsKey(pyramidButton.pyramid.ipnsKey))
                pyramidButton.stop()

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

        button = MultihashPyramidToolButton(pyramid, parent=self)
        action = self.addWidget(button)
        button.deleteRequest.connect(functools.partial(
            self.removePyramid, button, action))

        if pyramid.icon:
            ensure(self.fetchIcon(button, pyramid.icon))
        else:
            button.setIcon(getMimeIcon('unknown'))

        self.pyramids[pyramidPath] = button

    def publishNeeded(self, pyramidPath, mark):
        if pyramidPath in self.pyramids:
            pyramidMaster = self.pyramids[pyramidPath]
            pyramidMaster.needsPublish.emit(mark, True)

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

    def onAddPyramid(self):
        runDialog(AddMultihashPyramidDialog, self.app.marksLocal,
                  title='New multihash pyramid',
                  parent=self)


class MultihashPyramidToolButton(PopupToolButton):
    deleteRequest = pyqtSignal()
    changed = pyqtSignal()
    emptyNow = pyqtSignal()
    needsPublish = pyqtSignal(IPFSHashMark, bool)

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
        self._publishTimeout = 60 * 3
        self._pyrToolTip = None

        self.setAcceptDrops(True)
        self.setObjectName('pyramidMaster')

        self.clipboardItem = None
        self.app.clipTracker.currentItemChanged.connect(
            self.onClipboardItemChange)

        self.changed.connect(self.onPyrChange)
        self.emptyNow.connect(self.onPyrEmpty)
        self.needsPublish.connect(self.pyramidNeedsPublish)
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

        self.menu.addAction(self.openLatestAction)
        self.menu.addSeparator()

        self.menu.addAction(self.publishCurrentClipAction)
        self.menu.addSeparator()

        self.popItemAction = QAction(getIcon('pyramid-stack.png'),
                                     iPopItemFromPyramid(),
                                     self,
                                     triggered=self.onPopItem)
        self.popItemAction.setEnabled(False)
        self.menu.addAction(self.popItemAction)
        self.menu.addAction(getIcon('clipboard.png'),
                            iCopyIpnsAddress(),
                            self.onCopyIpns)
        self.menu.addAction(getIcon('ipfs-qrcode.png'),
                            iPyramidGenerateQr(),
                            self.onGenerateQrCode)
        self.menu.addSeparator()
        self.menu.addAction(
            getIcon('cancel.png'),
            iRemove(), lambda: self.deleteRequest.emit()
        )

        self.resetStyleSheet()
        self.initialize()
        self.watcherTask = self.app.task(self.publishWatcherTask)

    @property
    def pyramid(self):
        return self._pyramid

    @property
    def ipnsKeyPath(self):
        if self.pyramid.ipnsKey:
            return IPFSPath(joinIpns(self.pyramid.ipnsKey))

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
        log.debug('{pyramid}: {msg}'.format(
            pyramid=self.pyramid.path,
            msg=msg
        ))

    def info(self, msg):
        log.info('{pyramid}: {msg}'.format(
            pyramid=self.pyramid.path,
            msg=msg
        ))

    def stop(self):
        if self.watcherTask:
            try:
                self.watcherTask.cancel()
            except BaseException:
                self.debug('Could not cancel watcher task')

    def initialize(self):
        mark = self.app.marksLocal.pyramidGetLatestHashmark(self.pyramid.path)
        if mark:
            self.pyramidion = mark

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

    def onPyrChange(self):
        self.updateToolTip()

    def onPyrEmpty(self):
        self.pyramidion = None
        ensure(self.publishEmptyObject())

    def onGenerateQrCode(self):
        if self.ipnsKeyPath:
            ensure(self.generateQrCode(self.ipnsKeyPath))

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
            ensure(self.app.resourceOpener.open(objPath))

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
    async def generateQrCode(self, ipfsop, ipnsPath):
        encoder = IPFSQrEncoder()
        encoder.add(str(ipnsPath))

        qrName = 'ipfsqr.{}.png'.format(self.pyramid.ipnsKey)
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
            ipfsop.ctx.currentProfile.qrImageEncoded.emit(False, imgPath)

    @ipfsOp
    async def publishObject(self, ipfsop, objPath):
        return await ipfsop.publish(
            objPath,
            key=self.pyramid.ipnsKey,
            allow_offline=self.pyramid.ipnsAllowOffline,
            lifetime=self.pyramid.ipnsLifetime,
            timeout=self._publishTimeout
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

            self.info('publishing mark {mark} (obj: {obj}) to {ipns}'.format(
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

    def pyramidNeedsPublish(self, mark, notify):
        """
        We need to publish! Unless there's already a publish
        in progress, ensure an update right away
        """

        self.pyramidion = mark

        if self.publishInProgress is False:
            ensure(self.publish(self.pyramidion, notify))

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
                    delay = rand.randint(5, 30)

                    self.app.loop.call_later(
                        delay, self.needsPublish.emit, self.pyramidion, False)

                if isinstance(self.publishedLast, datetime):
                    delta = datetime.now() - self.publishedLast

                    if unpublishedMax and delta.seconds > unpublishedMax:
                        self.needsPublish.emit(self.pyramidion, True)

            await asyncio.sleep(3600)
