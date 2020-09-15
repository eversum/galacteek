from PyQt5.QtCore import QAbstractItemModel
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import Qt


class BaseAbstractItem(object):
    def __init__(self, data=None, parent=None):
        self.parentItem = parent
        self.itemData = data if data else []
        self.childItems = []

    def removeChildren(self, position, count):
        if position < 0 or position + count > len(self.childItems):
            return False

        for row in range(count):
            self.childItems.pop(position)

        return True

    def appendChild(self, item):
        self.childItems.append(item)

    def child(self, row):
        if row < 0 or row >= len(self.childItems):
            return None

        return self.childItems[row]

    def childCount(self):
        return len(self.childItems)

    def columnCount(self):
        return len(self.itemData)

    def data(self, column, role):
        try:
            return self.itemData[column]
        except IndexError:
            return None

    def userData(self, column):
        return None

    def parent(self):
        return self.parentItem

    def tooltip(self, col):
        return ''

    def icon(self, col):
        return None

    def row(self):
        if self.parentItem:
            return self.parentItem.childItems.index(self)

        return 0


class AbstractModel(QAbstractItemModel):
    def __init__(self, parent=None):
        super(AbstractModel, self).__init__(parent)

        self.rootItem = BaseAbstractItem([])

    def columnCount(self, parent):
        if parent.isValid():
            return parent.internalPointer().columnCount()
        else:
            return self.rootItem.columnCount()

    def data(self, index, role):
        if not index.isValid():
            return None

        item = index.internalPointer()

        specRoles = [
            Qt.DisplayRole,
            Qt.BackgroundRole,
            Qt.EditRole
        ]

        if role in specRoles:
            return item.data(index.column(), role)

        elif role == Qt.UserRole:
            return item.userData(index.column())

        elif role == Qt.DecorationRole:
            return item.icon(index.column())

        elif role == Qt.ToolTipRole:
            return item.tooltip(index.column())

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.rootItem.data(section, Qt.DisplayRole)

        return None

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item

        return self.rootItem

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

    def indexRoot(self):
        return self.createIndex(self.rootItem.row(), 0)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = index.internalPointer()
        if childItem is None:
            return QModelIndex()

        parentItem = childItem.parent()

        if parentItem == self.rootItem or not parentItem:
            return QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem)

    def rowCount(self, parent):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        if parentItem:
            return parentItem.childCount()
        else:
            print('NO PAREMT ITEM')
            return 0

    def removeRows(self, position, rows, parent=QModelIndex()):
        parentItem = self.getItem(parent)

        self.beginRemoveRows(parent, position, position + rows - 1)
        success = parentItem.removeChildren(position, rows)
        self.endRemoveRows()

        return success
