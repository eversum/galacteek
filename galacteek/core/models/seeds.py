import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QAbstractListModel
from PyQt5.QtCore import QAbstractItemModel
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QMimeData
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QVariant

from galacteek.core.models import BaseAbstractItem
from galacteek.ipfs.cidhelpers import getCID
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import cidConvertBase32

from galacteek.ui.helpers import getIcon
from galacteek.ui.helpers import getMimeIcon
from galacteek.ui.helpers import sizeFormat

from galacteek.ui.i18n import iUnixFSFileToolTip


class BaseItem(BaseAbstractItem):
    pass


class SeedsModel(QAbstractItemModel):
    def __init__(self, parent=None):
        super(SeedsModel, self).__init__(parent)

        self.app = QApplication.instance()
        self.seedsResults = []

        self.rootItem = BaseItem(['name'])

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def clearModel(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.seedsResults))
        self.seedsResults.clear()
        self.endRemoveRows()

    def rowCount(self, parent):
        return len(self.seedsResults)

    def columnCount(self, parent):
        return 1

    def index(self, row, column, parent=None):
        if not parent or not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def data(self, index, role):
        if not index.isValid():
            return QVariant(None)

        row = index.row()
        col = index.column()

        if role == Qt.DisplayRole:
            print('data', row, col)
            print(self.seedsResults)
            if row > len(self.seedsResults):
                return QVariant(None)

            s = self.seedsResults[row]
            return s['name']

        return super().data(index, role)
