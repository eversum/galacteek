import asyncio
import functools

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QDesktopWidget

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont

from galacteek import ensure
from galacteek.core.models.atomfeeds import AtomFeedEntryItem
from galacteek.core.models.atomfeeds import AtomFeedItem
from galacteek.dweb.page import BasePage

from . import ui_atomfeeds
from .dialogs import AddAtomFeedDialog
from .widgets import GalacteekTab
from .widgets import IPFSWebView
from .helpers import messageBox
from .helpers import runDialog


class EmptyPage(BasePage):
    def __init__(self, parent=None):
        super(EmptyPage, self).__init__('atomfeedsinit.html', parent=parent)


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
        self.emptyPage = EmptyPage(self)
        self.webView.setPage(self.emptyPage)

        self.ui = ui_atomfeeds.Ui_AtomFeeds()
        self.ui.setupUi(self)

        self.ui.hLayout.addWidget(self.webView)

        self.ui.addFeedButton.clicked.connect(self.onAddFeed)

        self.ui.treeFeeds.setModel(self.model)

        self.fontFeeds = QFont('Times', 14, QFont.Bold)
        self.fontBold = QFont('Times', 12, QFont.Bold)
        self.fontRead = QFont('Times', 12)

        self.ui.treeFeeds.header().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self.ui.treeFeeds.setSortingEnabled(True)
        self.ui.treeFeeds.sortByColumn(1, Qt.DescendingOrder)

        self.ui.treeFeeds.clicked.connect(self.onItemClicked)

        self.ui.treeFeeds.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeFeeds.customContextMenuRequested.connect(
            self.onContextMenu)

        self.ui.treeFeeds.setMinimumSize(QSize(
            self.desktopGeometry.width() / 3,
            self.desktopGeometry.height())
        )
        self.ui.treeFeeds.setMaximumSize(QSize(
            self.desktopGeometry.width() / 2,
            self.desktopGeometry.height())
        )
        self.webView.setMinimumSize(QSize(
            self.desktopGeometry.width() / 2,
            self.desktopGeometry.height())
        )

        self.model.feedEntryAdded.connect(self.onEntryAdded)
        self.ui.treeFeeds.setRootIndex(self.model.itemRootIdx)

    def onContextMenu(self, point):
        idx = self.ui.treeFeeds.indexAt(point)
        if not idx.isValid():
            return

        item = self.model.itemFromIndex(idx)

        if isinstance(item, AtomFeedItem):
            menu = QMenu()
            menu.addAction('Remove feed',
                           functools.partial(self.removeFeed, item))

            menu.exec(self.ui.treeFeeds.mapToGlobal(point))

    def removeFeed(self, feedItem):
        ensure(self.app.sqliteDb.feeds.unfollow(
            feedItem.feedId))

    def onAddFeed(self):
        def urlAccepted(dlg):
            url = dlg.textValue()
            qUrl = QUrl(url)

            if not qUrl.isValid() or not qUrl.scheme():
                return messageBox('Invalid URL')

            ensure(self.app.mainWindow.atomButton.atomFeedSubscribe(url))

        runDialog(AddAtomFeedDialog, accepted=urlAccepted)

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
