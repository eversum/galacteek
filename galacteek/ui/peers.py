import os.path
import asyncio

from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtWidgets import QWidget

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QMimeData
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QAbstractItemView

from galacteek import ensure, log
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import *
from galacteek.ipfs.ipfsops import *
from galacteek.core.modelhelpers import *
from galacteek.dweb.atom import DWEB_ATOM_FEEDFN

from . import ui_peersmgr
from .widgets import *
from .helpers import *
from .dialogs import *


def iUsername():
    return QCoreApplication.translate('PeersManager', 'Username')


def iPeerId():
    return QCoreApplication.translate('PeersManager', 'Peer ID')


def iPingAvg():
    return QCoreApplication.translate('PeersManager', 'Ping Average (ms)')


def iLocation():
    return QCoreApplication.translate('PeersManager', 'Location')


def iInvalidDagCID(dagCid):
    return QCoreApplication.translate('PeersManager',
                                      'Invalid DAG CID: {0}').format(dagCid)


class PeersModel(QStandardItemModel):
    def mimeData(self, indexes):
        mimedata = QMimeData()

        for idx in indexes:
            idxPeer = self.index(idx.row(), 1, idx.parent())
            if idxPeer.isValid():
                peer = self.data(idxPeer)
                mimedata.setUrls([QUrl('galacteekpeer:{}'.format(peer))])
                break

        return mimedata

    def canDropMimeData(self, data, action, row, column, parent):
        return True

    def dropMimeData(self, data, action, row, column, parent):
        if data.hasUrls():
            return True


class PeersTracker(QObject):
    def __init__(self, ctx):
        super().__init__()
        self.model = PeersModel()
        self.model.setHorizontalHeaderLabels([
            iUsername(),
            iPeerId(),
            iPingAvg(),
            iLocation(),
            ''
        ])
        self.ctx = ctx
        self.ctx.peers.changed.connect(self.onPeersChange)
        self.ctx.peers.peerAdded.connect(self.onPeerAdded)
        self.ctx.peers.peerModified.connect(self.onPeerModified)
        self.ctx.peers.peerLogout.connect(self.onPeerLogout)
        self._peersRows = {}

    @property
    def modelRoot(self):
        return self.model.invisibleRootItem()

    @property
    def peersRows(self):
        return self._peersRows

    def onPeerLogout(self, peerId):
        modelSearch(self.model,
                    parent=self.modelRoot.index(),
                    search=peerId, delete=True)
        if peerId in self._peersRows:
            del self._peersRows[peerId]

    def onPeerModified(self, peerId):
        peerCtx = self.ctx.peers.getByPeerId(peerId)
        if not peerCtx:
            return

        row = self._peersRows.get(peerId, None)
        if row:
            row[0].setText(peerCtx.ident.username)
            row[1].setText(peerId)
            row[3].setText(peerCtx.ident.location)

    def onPeerAdded(self, peerId):
        peerCtx = self.ctx.peers.getByPeerId(peerId)
        if not peerCtx:
            return

        self.addPeerFromEntry(peerId, peerCtx)

    def addPeerFromEntry(self, peerId, peerCtx):
        row = [
            UneditableItem(peerCtx.ident.username),
            UneditableItem(peerId),
            UneditableItem(str(peerCtx.pingavg)),
            UneditableItem(peerCtx.ident.location),
            UneditableItem(''),
        ]
        rowStatus = [
            UneditableItem('Joined: {0}'.format(peerCtx.ident.dateCreated)),
            UneditableItem(peerId),
        ]

        self.modelRoot.appendRow(row)
        row[0].appendRow(rowStatus)
        self._peersRows[peerId] = row

    def onPeersChange(self):
        pass


class PeersManager(GalacteekTab):
    def __init__(self, gWindow, peersTracker, **kw):
        super().__init__(gWindow, **kw)

        self.lock = asyncio.Lock()
        self.peersTracker = peersTracker

        self.peersWidget = QWidget()
        self.addToLayout(self.peersWidget)
        self.ui = ui_peersmgr.Ui_PeersManager()
        self.ui.setupUi(self.peersWidget)

        self.ui.tree.setModel(self.peersTracker.model)
        self.ui.tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.ui.tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.ui.tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)

        self.ui.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.tree.customContextMenuRequested.connect(self.onContextMenu)
        self.ui.tree.doubleClicked.connect(self.onDoubleClick)
        self.ui.tree.setDragDropMode(QAbstractItemView.DragOnly)

        self.ui.search.returnPressed.connect(self.onSearch)

        self.app.ipfsCtx.peers.changed.connect(self.onPeersChange)
        self.app.ipfsCtx.peers.peerAdded.connect(self.onPeerAdded)
        ensure(self.refreshControls())

    @property
    def model(self):
        return self.peersTracker.model

    def onSearch(self):
        search = self.ui.search.text()
        if len(search) > 0:
            self.ui.tree.keyboardSearch(search)

    def onPeersChange(self):
        self.ui.peersCountLabel.setText(str(self.app.ipfsCtx.peers.peersCount))

    def onPeerAdded(self, peerId):
        ensure(self.refreshControls())

    async def refreshControls(self):
        def onPeerAction(idx, id):
            peerCtx = self.peersTracker.ctx.peers.getByPeerId(id)
            if idx in [0, 1]:
                method = 'ipns' if idx == 1 else 'direct'
                ensure(self.explorePeerHome(peerCtx, method=method))
            elif idx == 2:
                ensure(self.followPeerFeed(peerCtx))

        def followPeer(id):
            peerCtx = self.peersTracker.ctx.peers.getByPeerId(id)

            runDialog(AddFeedDialog, self.app.marksLocal,
                      joinIpns(peerCtx.ident.dagIpns),
                      feedName=peerCtx.ident.username)

        with await self.lock:
            for peerId, row in self.peersTracker.peersRows.items():
                idx = self.model.indexFromItem(row[4])
                if self.ui.tree.indexWidget(idx) is not None:
                    continue

                btnHomeCombo = QComboBox()
                btnHomeCombo.addItem('Browse homepage (direct)')
                btnHomeCombo.addItem('Browse homepage (IPNS)')
                btnHomeCombo.addItem('Follow (Atom feed)')
                btnHomeCombo.activated.connect(
                    lambda idx: onPeerAction(idx, peerId))

                self.ui.tree.setIndexWidget(idx, btnHomeCombo)

    def onContextMenu(self, point):
        idx = self.ui.tree.indexAt(point)
        if not idx.isValid():
            return

        menu = QMenu(self)
        menu.exec(self.ui.tree.mapToGlobal(point))

    def onDoubleClick(self, idx):
        idxPeerId = self.model.sibling(idx.row(), 1, idx)
        peerId = self.model.data(idxPeerId)
        peerCtx = self.peersTracker.ctx.peers.getByPeerId(peerId)

        ensure(self.explorePeerHome(peerCtx))

    @ipfsOp
    async def followPeerFeed(self, op, peerCtx):
        identMsg = peerCtx.ident
        path = os.path.join(joinIpns(identMsg.dagIpns), DWEB_ATOM_FEEDFN)
        ipfsPath = IPFSPath(path)

        try:
            await self.app.sqliteDb.feeds.follow(ipfsPath.dwebUrl)
        except Exception:
            # TODO
            pass

    @ipfsOp
    async def explorePeerHome(self, op, peerCtx, method='direct'):
        identMsg = peerCtx.ident

        dagCid = identMsg.dagCid
        if not cidValid(dagCid):
            log.debug('invalid DAG CID: {}'.format(dagCid))
            return messageBox(iInvalidDagCID(dagCid))

        if method == 'ipns':
            self.gWindow.addBrowserTab().browseFsPath(
                os.path.join(joinIpns(identMsg.dagIpns), 'index.html'))
        elif method == 'direct':
            self.gWindow.addBrowserTab().browseFsPath(
                os.path.join(joinIpfs(identMsg.dagCid), 'index.html'))
