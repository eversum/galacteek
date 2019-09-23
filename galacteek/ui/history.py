from PyQt5.QtWidgets import QTreeView
from PyQt5.QtWidgets import QApplication

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import Qt

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtGui import QBrush
from PyQt5.QtGui import QColor

from galacteek import ensure
from galacteek.core.modelhelpers import UneditableItem

from .i18n import iUnknown
from .i18n import iHashmarks


class URLHistory(QObject):
    historyConfigChanged = pyqtSignal(bool)

    def __init__(self, db, enabled=False, parent=None):
        super(URLHistory, self).__init__(parent)
        self.db = db
        self.enabled = enabled
        self.historyConfigChanged.connect(self.onConfig)

    def onConfig(self, enableHistory):
        self.enabled = enableHistory

    def record(self, url, title):
        if self.enabled:
            ensure(self.db.historyRecord(url, title))

    def clear(self):
        ensure(self.db.historyClear())

    async def match(self, input):
        return await self.db.historySearch(input)


class HistoryMatchesWidget(QTreeView):
    historyItemSelected = pyqtSignal(str)
    collapsed = pyqtSignal()

    def __init__(self, parent=None):
        super(HistoryMatchesWidget, self).__init__(parent)

        self.app = QApplication.instance()
        self.setObjectName('historySearchResults')
        self.clicked.connect(self.onItemActivated)

        self.model = QStandardItemModel()
        self.setModel(self.model)
        self.setHeaderHidden(True)

    def onItemActivated(self, idx):
        idxUrl = self.model.index(idx.row(), 1, idx.parent())
        data = self.model.data(idxUrl)

        if isinstance(data, str) and data:
            self.historyItemSelected.emit(data)

    def showMatches(self, marks, hMatches):
        self.model.clear()
        brush = QBrush(QColor('lightgrey'))

        mItem = UneditableItem(iHashmarks())
        mItem.setBackground(brush)
        mItemE = UneditableItem('')
        mItemE.setBackground(brush)
        self.model.invisibleRootItem().appendRow([mItem, mItemE])

        for match in marks:
            title = match['title'][0:64] if match['title'] else iUnknown()

            itemT = UneditableItem(title)
            item = UneditableItem(match['url'])
            item.setToolTip(match['url'])
            item.setData(match['url'], Qt.EditRole)

            mItem.appendRow([itemT, item])

        hItem = UneditableItem('History items')
        hItemE = UneditableItem('')
        hItem.setBackground(brush)
        hItemE.setBackground(brush)
        self.model.invisibleRootItem().appendRow([hItem, hItemE])

        for match in hMatches:
            title = match['title'][0:64] if match['title'] else iUnknown()
            itemT = UneditableItem(title)

            item = UneditableItem(match['url'])
            item.setToolTip(match['url'])
            item.setData(match['url'], Qt.EditRole)

            hItem.appendRow([itemT, item])

        self.expandAll()
        self.resizeColumnToContents(0)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return:
            # The 'activated' signal does not seem to have the same
            # behavior across platforms so we handle Return manually here
            curIdx = self.currentIndex()
            if curIdx.isValid():
                self.onItemActivated(curIdx)
        elif event.key() == Qt.Key_Escape:
            self.hide()
            self.collapsed.emit()
        else:
            super(HistoryMatchesWidget, self).keyPressEvent(event)
