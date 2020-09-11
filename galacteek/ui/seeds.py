import os.path
import asyncio

from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QCompleter
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QDockWidget
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QAbstractItemView
from PyQt5.QtWidgets import QTreeView
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QLineEdit

from PyQt5.QtCore import QAbstractItemModel
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import QMimeData
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QVariant
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QBuffer
from PyQt5.QtCore import QByteArray
from PyQt5.QtCore import QIODevice

from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QBrush

from galacteek import ensure
from galacteek import partialEnsure
from galacteek import log
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import *
from galacteek.ipfs.ipfsops import *
from galacteek.core.modelhelpers import *
from galacteek.core.models import BaseAbstractItem
from galacteek.core.models.seeds import SeedsModel
from galacteek.core.iphandle import SpaceHandle
from galacteek.dweb.atom import DWEB_ATOM_FEEDFN
from galacteek.did import didExplode
from galacteek.did.ipid import IPService

from .dids import buildIpServicesMenu
from . import ui_peersmgr
from .widgets import *
from .helpers import *
from .dialogs import *
from .i18n import iIPIDLong
from .i18n import iIPServices
from .i18n import iFollow
from .i18n import iUnknown
from .i18n import iIPHandle


ItemTypeRole = Qt.UserRole + 1
PeerIdRole = Qt.UserRole + 2
PeerDidRole = Qt.UserRole + 3
PeerHandleRole = Qt.UserRole + 4


class PeerBaseItem(BaseAbstractItem):
    itemType = None

    def tooltip(self, col):
        return ''

    def icon(self):
        return getIcon('unknown-file.png')


class PeerTreeItem(PeerBaseItem):
    itemType = 'peer'

    def __init__(self, piCtx, parent=None):
        super(PeerTreeItem, self).__init__(data=None, parent=parent)
        self.ctx = piCtx

    def columnCount(self):
        return 2

    def userData(self, column):
        return self.ctx.peerId

    def tooltip(self, col):
        handle = SpaceHandle(self.ctx.iphandle)

        try:
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.WriteOnly)
            self.ctx.avatarPixmapScaled(128, 128).save(buffer, 'PNG')
            buffer.close()

            avatarUrl = 'data:image/png;base64, {}'.format(
                bytes(buffer.data().toBase64()).decode()
            )
        except Exception:
            avatarUrl = ':/share/icons/unknown-file.png'

        return iPeerToolTip(
            avatarUrl,
            self.ctx.peerId,
            str(handle),
            self.ctx.ipid.did,
            self.ctx.validated,
            self.ctx.authenticated,
            self.ctx.pingAvg()
        )

    def data(self, column, role):
        handle = self.ctx.spaceHandle

        if role == Qt.DisplayRole or role == Qt.EditRole:
            if column == 0:
                if handle.valid:
                    return handle.short
                else:
                    return iUnknown()
            if column == 1:
                return self.ctx.ipid.did

        elif role == Qt.BackgroundRole:
            if self.ctx.ipid.local:
                color = QColor('#cce4ff')
            else:
                if self.ctx.alive():
                    color = QColor('#90C983')
                else:
                    color = QColor('#F0F7F7')
            return QBrush(color)
        elif role == PeerIdRole:
            return self.ctx.peerId
        elif role == PeerDidRole:
            return self.ctx.ipid.did
        elif role == PeerHandleRole:
            return str(handle)

        return QVariant(None)

    async def updateServices(self):
        esids = [it.service.id for it in self.childItems]

        async for service in self.ctx.ipid.discoverServices():
            if service.id in esids:
                if service.container:
                    for it in self.childItems:
                        if it.service.id == service.id:
                            await it.updateContained()

                continue

            pSItem = PeerServiceTreeItem(service, parent=self)
            self.appendChild(pSItem)

            if service.container:
                await pSItem.updateContained()

    def icon(self):
        if self.ctx.alive():
            return self.ctx.avatarPixmapScaled(32, 32)
        else:
            return getIcon('offline.png')


class SeedsTrackerTab(GalacteekTab):
    def __init__(self, gWindow):
        super().__init__(gWindow, sticky=True)

        self.model = SeedsModel(self)

        self.view = QTreeView()

        self.searchLine = QLineEdit()
        self.searchLine.returnPressed.connect(
            partialEnsure(self.onSearch))

        self.addToLayout(self.searchLine)
        self.addToLayout(self.view)

        self.view.setModel(self.model)


    @ipfsOp
    async def onSearch(self, ipfsop):
        profile = ipfsop.ctx.currentProfile
        text = self.searchLine.text()

        if text:
            self.model.clearModel()

            seedsDag = profile.dagSeedsAll

            async for result in seedsDag.search(text):
                self.model.seedsResults.append({
                    'name': result[0]
                })
                print(result)

            print(self.model.seedsResults)

            self.model.modelReset.emit()
