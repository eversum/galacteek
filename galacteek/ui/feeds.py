import asyncio

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QDesktopWidget

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QSortFilterProxyModel

from galacteek import ensure
from galacteek import partialEnsure
from galacteek.core.models.atomfeeds import AtomFeedEntryItem
from galacteek.core.models.atomfeeds import AtomFeedItem
from galacteek.dweb.page import BasePage

from . import ui_atomfeeds
from .dialogs import AddAtomFeedDialog
from .widgets import GalacteekTab
from .widgets import IPFSWebView
from .helpers import runDialogAsync


class EmptyPage(BasePage):
    pass


class NumericSortProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super(NumericSortProxyModel, self).__init__(parent)

    def lessThan(self, left, right):
        leftData = self.sourceModel().data(left)
        rightData = self.sourceModel().data(right)

        try:
            return int(leftData) < int(rightData)
        except ValueError:
            return leftData < rightData


class AtomFeedsView(QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.clipboard = self.app.appClipboard

        self.desktopWidget = QDesktopWidget()
        self.desktopGeometry = self.desktopWidget.screenGeometry()

        self.lock = asyncio.Lock()
        self.model = model
        self._offlineMode = False

        self.webView = IPFSWebView(parent=self)
        self.emptyPage = EmptyPage(
            'atomfeedsinit.html', parent=self, navBypassLinks=True)
        self.webView.setPage(self.emptyPage)

        self.ui = ui_atomfeeds.Ui_AtomFeeds()
        self.ui.setupUi(self)

        self.ui.hLayout.addWidget(self.webView)

        self.ui.addFeedButton.clicked.connect(self.onAddFeed)

        self.ui.treeFeeds.setModel(self.model)
        self.ui.treeFeeds.setSortingEnabled(False)

        self.fontFeeds = QFont('Times', 14, QFont.Bold)
        self.fontBold = QFont('Times', 12, QFont.Bold)
        self.fontRead = QFont('Times', 12)

        self.ui.treeFeeds.header().setSectionResizeMode(
            QHeaderView.ResizeToContents)

        self.ui.treeFeeds.clicked.connect(self.onItemClicked)

        self.ui.treeFeeds.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeFeeds.customContextMenuRequested.connect(
            self.onContextMenu)

        self.ui.treeFeeds.setMinimumWidth(
            self.desktopGeometry.width() / 3,
        )
        self.ui.treeFeeds.setMaximumSize(QSize(
            self.desktopGeometry.width() / 2,
            self.desktopGeometry.height())
        )
        self.webView.setMinimumWidth(
            self.desktopGeometry.width() / 2
        )

        self.model.feedEntryAdded.connect(self.onEntryAdded)
        self.ui.treeFeeds.setRootIndex(self.model.itemRootIdx)

    def onContextMenu(self, point):
        idx = self.ui.treeFeeds.indexAt(point)
        if not idx.isValid():
            return

        item = self.model.itemFromIndex(idx)

        if isinstance(item, AtomFeedItem):
            menu = QMenu(self)
            menu.addAction('Mark all as read',
                           partialEnsure(self.onMarkAllRead, item))
            menu.addAction('Remove feed',
                           partialEnsure(self.onRemoveFeed, item))
            menu.addSeparator()

            menu.exec(self.ui.treeFeeds.mapToGlobal(point))

    async def onRemoveFeed(self, feedItem):
        await self.app.sqliteDb.feeds.unfollow(feedItem.feedId)
        self.model.updateRoot()

    async def onMarkAllRead(self, feedItem):
        for item in feedItem.childrenItems():
            if isinstance(item, AtomFeedEntryItem):
                self.model.markEntryAsRead(item)
                item.setFont(self.fontRead)

            await asyncio.sleep(0)

        feedItem.updateTitle()

    def onAddFeed(self):
        def urlAccepted(dlg):
            url = dlg.textValue()
            ensure(self.app.mainWindow.atomButton.atomFeedSubscribe(url))

        ensure(runDialogAsync(AddAtomFeedDialog, accepted=urlAccepted))

    def onEntryAdded(self, entryItem):
        if entryItem.entry.status == entryItem.entry.ENTRY_STATUS_NEW:
            entryItem.setFont(self.fontBold)
        else:
            entryItem.setFont(self.fontRead)

        parent = entryItem.parent()
        if isinstance(parent, AtomFeedItem):
            parent.updateTitle()
            parent.setFont(self.fontFeeds)

    def onItemClicked(self, idx):
        item = self.model.itemFromIndex(idx)

        if isinstance(item, AtomFeedEntryItem):
            url = QUrl(item.entry.id)
            if url.isValid():
                self.webView.load(url)

            self.model.markEntryAsRead(item)
            item.setFont(self.fontRead)
            item.parent().updateTitle()


class AtomFeedsViewTab(GalacteekTab):
    def __init__(self, gWindow, view=None):
        super(AtomFeedsViewTab, self).__init__(gWindow)

        self.view = view if view else AtomFeedsView(
            self.app.modelAtomFeeds, parent=self)
        self.addToLayout(self.view)
