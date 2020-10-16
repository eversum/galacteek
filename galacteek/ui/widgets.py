import asyncio
import attr
from datetime import datetime

from PyQt5.QtWidgets import QFrame
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QSpacerItem
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QWidgetAction
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtWidgets import QListView
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtWidgets import QPlainTextEdit
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QTextBrowser
from PyQt5.QtWidgets import QToolTip

from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEnginePage

from PyQt5.QtCore import QRect
from PyQt5.QtCore import QEvent
from PyQt5.QtCore import QFileInfo
from PyQt5.QtCore import QRegExp
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QMimeData
from PyQt5.QtCore import QSize
from PyQt5.QtCore import QFile
from PyQt5.QtCore import QIODevice
from PyQt5.QtCore import QVariant
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QByteArray
from PyQt5.QtCore import QBuffer

from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QTextCursor
from PyQt5.QtGui import QKeySequence

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name

from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.mimetype import detectMimeType
from galacteek import log
from galacteek import ensure
from galacteek import partialEnsure
from galacteek.core.asynclib import asyncify
from galacteek.core import utcDatetime
from galacteek.dweb.markdown import markitdown

from galacteek import database
from galacteek.database.models.core import Hashmark

from .helpers import getIcon
from .helpers import getMimeIcon
from .helpers import getIconFromIpfs
from .helpers import getImageFromIpfs
from .helpers import sizeFormat
from .helpers import messageBox
from .helpers import messageBoxAsync
from .helpers import inputTextCustom

from .i18n import iCancel
from .i18n import iUnknown
from .i18n import iHashmarksDatabase
from .i18n import iSearchHashmarks
from .i18n import iSearchHashmarksAllAcross
from .i18n import iSearchUseShiftReturn
from .i18n import iHashmarkInfoToolTip
from .i18n import iHashmarkSources
from .i18n import iHashmarkSourcesDbSync
from .i18n import iHashmarkSourcesAddGitRepo
from .i18n import iHashmarkSourcesAddLegacyIpfsMarks
from .i18n import iHashmarkSourceAlreadyRegistered
from .i18n import iIPFSUrlTypeNative
from .i18n import iIPFSUrlTypeHttpGateway


@attr.s(auto_attribs=True)
class TabContext(object):
    tabIdent: str = ''


class GalacteekTab(QWidget):
    def __init__(self, gWindow, parent=None,
                 vLayout=True, sticky=False, ctx=None):
        super(GalacteekTab, self).__init__(parent)

        self.app = QApplication.instance()

        if vLayout is True:
            self.vLayout = QVBoxLayout(self)
            self.setLayout(self.vLayout)

        self.gWindow = gWindow
        self._workspace = None
        self._ctx = ctx if ctx else TabContext()
        self.sticky = sticky
        self.setAttribute(Qt.WA_DeleteOnClose)

    @property
    def workspace(self):
        return self._workspace

    @property
    def ctx(self):
        return self._ctx

    @property
    def loop(self):
        return self.app.loop

    @property
    def profile(self):
        return self.app.ipfsCtx.currentProfile

    def workspaceAttach(self, ws):
        self._workspace = ws

    def tabIndex(self, w=None):
        return self.workspace.tabWidget.indexOf(w if w else self)

    def tabRemove(self):
        idx = self.tabIndex()
        if idx >= 0:
            self.workspace.tabWidget.tabCloseRequested.emit(idx)

    def setTabName(self, name, widget=None):
        idx = self.tabIndex(w=widget)
        if idx >= 0:
            self.workspace.tabWidget.setTabText(idx, name)

    def setTabIcon(self, icon, widget=None):
        idx = self.tabIndex(w=widget)
        if idx >= 0:
            self.workspace.tabWidget.setTabIcon(idx, icon)

    def tabBar(self):
        return self.workspace.tabWidget.tabBar()

    def addToLayout(self, widget):
        self.vLayout.addWidget(widget)

    async def onClose(self):
        return True

    async def onTabChanged(self):
        return True

    def tabActiveNotify(self):
        if self.workspace:
            self.workspace.stack.wsActivityNotify(self.workspace)

    @ipfsOp
    async def initialize(self, op):
        pass

    def tabDropEvent(self, event):
        pass


class HorizontalLine(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
        self.setStyleSheet('''
            QFrame {
                background-color: #4a9ea1;
            }
        ''')


class URLDragAndDropProcessor:
    fileDropped = pyqtSignal(QUrl)
    ipfsObjectDropped = pyqtSignal(IPFSPath)

    def dragEnterEvent(self, event):
        mimeData = event.mimeData()

        if mimeData.hasUrls() or mimeData.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mimeData = event.mimeData()

        if mimeData is None:
            return

        if mimeData.hasUrls():
            for url in mimeData.urls():
                if not url.isValid():
                    continue

                if url.scheme() == 'file' and url.isValid():
                    self.fileDropped.emit(url)
                else:
                    path = IPFSPath(url.toString(), autoCidConv=True)
                    if path.valid:
                        self.ipfsObjectDropped.emit(path)
        elif mimeData.hasText():
            text = mimeData.text()
            path = IPFSPath(text, autoCidConv=True)

            if path.valid:
                self.ipfsObjectDropped.emit(path)

        event.acceptProposedAction()

    @ipfsOp
    async def importDroppedFileFromUrl(self, ipfsop, url,
                                       maxFileSize=2 * 1024 * 1024):
        try:
            path = url.toLocalFile()
            fileInfo = QFileInfo(path)

            if fileInfo.isFile():
                file = QFile(path)

                if file.open(QIODevice.ReadOnly):
                    size = file.size()

                    if size and size < maxFileSize:
                        entry = await ipfsop.addPath(path)
                        file.close()

                        if entry:
                            return entry

                    file.close()
        except Exception:
            pass


class CheckableToolButton(QToolButton):
    def __init__(self, toggled=None, icon=None, parent=None):
        super(CheckableToolButton, self).__init__(parent)
        self.setCheckable(True)
        self.setAutoRaise(True)

        if toggled:
            self.toggled.connect(toggled)

        if icon:
            self.setIcon(icon)


class IPFSPathClipboardButton(QToolButton):
    def __init__(self, ipfsPath, parent=None):
        super(IPFSPathClipboardButton, self).__init__(parent)

        self.setEnabled(False)
        self.setIcon(getIcon('clipboard.png'))
        self.app = QApplication.instance()
        self.path = ipfsPath
        self.clicked.connect(self.onClicked)

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, path):
        if isinstance(path, IPFSPath) and path.valid:
            self.setEnabled(True)
            self.setToolTip('Copy to clipboard: {}'.format(str(path)))
            self._path = path

    def onClicked(self):
        if isinstance(self.path, IPFSPath) and self.path.valid:
            self.app.setClipboardText(str(self.path))


class IPFSUrlLabel(QLabel):
    def __init__(self, ipfsPath, invalidPathLabel='Invalid path', parent=None):
        super(IPFSUrlLabel, self).__init__(parent)
        self.app = QApplication.instance()

        self.invalidPathMessage = invalidPathLabel
        self.path = ipfsPath
        self.linkActivated.connect(self.onLinkClicked)

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, val):
        self._path = val

        if self.path and self.path.valid:
            self.url = QUrl(self.path.ipfsUrl)
            self.setText('<a href="{url}">{url}</a>'.format(
                url=self.url.toString()))
        else:
            self.url = None
            self.setText(self.invalidPathMessage)

    def dragEnterEvent(self, event):
        mimeData = event.mimeData()

        if mimeData.hasUrls() or mimeData.hasText():
            event.acceptProposedAction()

    def mimeData(self, indexes):
        mimedata = QMimeData()
        mimedata.setUrls([self.url])
        return mimedata

    def onLinkClicked(self, urlString):
        ensure(self.app.resourceOpener.open(self.path))


class LabelWithURLOpener(QLabel):
    """
    QLabel which opens http/https URLs in a tab.
    Used by the 'About' dialog
    """

    def __init__(self, text, parent=None):
        super(LabelWithURLOpener, self).__init__(text, parent)
        self.app = QApplication.instance()
        self.linkActivated.connect(self.onLinkClicked)

    def onLinkClicked(self, urlString):
        url = QUrl(urlString)
        if url.isValid() and url.scheme() in ['http', 'https']:
            tab = self.app.mainWindow.addBrowserTab()
            tab.enterUrl(url)


class PopupToolButton(QToolButton, URLDragAndDropProcessor):
    def __init__(self, icon=None, parent=None, menu=None,
                 mode=QToolButton.MenuButtonPopup, acceptDrops=False,
                 menuSizeHint=None, toolTipsVisible=True):
        super(PopupToolButton, self).__init__(parent)

        self.menu = menu if menu else QMenu(self)
        self.menu.setToolTipsVisible(toolTipsVisible)
        self.setPopupMode(mode)
        self.setMenu(self.menu)
        self.setAcceptDrops(acceptDrops)

        if icon:
            self.setIcon(icon)


class IPFSObjectToolButton(QToolButton):
    """
    Used in the quickaccess toolbar
    """
    deleteRequest = pyqtSignal()

    def __init__(self, ipfsPath, icon=None, parent=None):
        super(IPFSObjectToolButton, self).__init__(parent=parent)
        self.setObjectName('qaToolButton')
        if icon:
            self.setIcon(icon)

    def mousePressEvent(self, event):
        button = event.button()

        if button == Qt.RightButton:
            menu = QMenu(self)
            menu.addAction('Remove', lambda: self.deleteRequest.emit())
            menu.exec(self.mapToGlobal(event.pos()))

        super().mousePressEvent(event)


class QAObjTagItemToolButton(QToolButton):
    """
    Used in the quickaccess toolbar
    """
    deleteRequest = pyqtSignal()

    def __init__(self, item, icon=None, parent=None):
        super(QAObjTagItemToolButton, self).__init__(parent=parent)
        self.app = QApplication.instance()
        if icon:
            self.setIcon(icon)

        self.item = item
        self.clicked.connect(lambda: ensure(self.onClicked()))

    async def hashmark(self):
        return await database.hashmarksByObjTagLatest(self.item.tag)

    async def onClicked(self):
        hashmark = await self.hashmark()
        if hashmark:
            ensure(self.app.resourceOpener.open(
                hashmark.path,
                openingFrom='qa',
                schemePreferred=hashmark.schemepreferred
            ))

    def mousePressEvent(self, event):
        button = event.button()

        if button == Qt.RightButton:
            menu = QMenu(self)
            menu.addAction('Remove', lambda: self.deleteRequest.emit())
            menu.exec(self.mapToGlobal(event.pos()))

        super().mousePressEvent(event)


class HashmarkThisButton(QToolButton):
    def __init__(self, ipfsPath: IPFSPath, parent=None):
        super(HashmarkThisButton, self).__init__(parent=parent)
        self.setIcon(getIcon('hashmarks.png'))
        self._ipfsPath = ipfsPath
        self.clicked.connect(self.onClicked)
        self.setToolTip(
            'Hashmark object: {}'.format(str(self.ipfsPath)))

    @property
    def ipfsPath(self):
        return self._ipfsPath

    @ipfsPath.setter
    def ipfsPath(self, path: IPFSPath):
        self._ipfsPath = path

        if self.ipfsPath.valid:
            self.setToolTip(
                'Hashmark object: {}'.format(str(self.ipfsPath)))

    def onClicked(self):
        from .hashmarks import addHashmarkAsync
        ensure(addHashmarkAsync(str(self.ipfsPath)))


class HashmarkToolButton(QToolButton):
    """
    Used in the quickaccess toolbar
    """
    deleteRequest = pyqtSignal()

    def __init__(self, mark, icon=None, parent=None):
        super(HashmarkToolButton, self).__init__(parent=parent)
        self.setObjectName('qaToolButton')
        if icon:
            self.setIcon(icon)

        self._hashmark = mark

    async def hashmark(self):
        return self._hashmark

    def mousePressEvent(self, event):
        button = event.button()

        if button == Qt.RightButton:
            menu = QMenu(self)
            menu.addAction('Remove', lambda: self.deleteRequest.emit())
            menu.exec(self.mapToGlobal(event.pos()))

        super().mousePressEvent(event)


class _HashmarksCommon:
    def makeHashmarkAction(self, mark, loadIcon=True):
        tLenMax = 48

        path = mark.uri
        title = mark.title

        if title and len(title) > tLenMax:
            title = '{0} ...'.format(title[0:tLenMax])

        action = QAction(title, self)
        action.setToolTip(iHashmarkInfoToolTip(mark))

        action.setData({
            'path': path,
            'mark': mark,
            'iconpath': mark.icon.path if mark.icon else None
        })

        if not mark.icon or not loadIcon:
            # Default icon
            action.setIcon(getIcon('ipfs-logo-128-white-outline.png'))
        else:
            ensure(self.loadMarkIcon(action, mark.icon.path))

        return action

    @ipfsOp
    async def loadMarkIcon(self, ipfsop, action, iconCid):
        data = action.data()

        if isinstance(data, dict) and 'iconloaded' in data:
            return

        icon = await getIconFromIpfs(ipfsop, iconCid)

        if icon:
            await ipfsop.sleep()

            action.setIcon(icon)
            data['iconloaded'] = True
            action.setData(data)


class HashmarkMgrButton(PopupToolButton, _HashmarksCommon):
    hashmarkClicked = pyqtSignal(Hashmark)

    def __init__(self, marks, iconFile='hashmarks.png',
                 maxItemsPerCategory=128, parent=None):
        super(HashmarkMgrButton, self).__init__(parent=parent,
                                                mode=QToolButton.InstantPopup)

        self.app = QApplication.instance()
        self.setObjectName('hashmarksMgrButton')
        self.setIcon(getIcon(iconFile))
        self.setupMenu()

        self.hCount = 0
        self.marks = marks
        self.cMenus = {}
        self.maxItemsPerCategory = maxItemsPerCategory

        database.HashmarkAdded.connectTo(self.onMarkAdded)
        database.HashmarkDeleted.connectTo(self.onMarkDeleted)

    def setupMenu(self):
        self.menu.setObjectName('hashmarksMgrMenu')
        self.menu.setToolTipsVisible(True)

        self.sourcesMenu = QMenu(iHashmarkSources())
        self.sourcesMenu.setIcon(self.icon())

        self.popularTagsMenu = QMenu('Popular Tags')
        self.popularTagsMenu.setObjectName('popularTagsMenu')
        self.popularTagsMenu.setIcon(getIcon('hash.png'))
        self.popularTagsMenu.aboutToShow.connect(
            partialEnsure(self.onShowPopularTags))

        self.syncAction = QAction(
            self.icon(),
            iHashmarkSourcesDbSync(),
            self.sourcesMenu,
            triggered=lambda: ensure(self.onSynchronize())
        )

        self.addGitSourceAction = QAction(
            self.icon(),
            iHashmarkSourcesAddGitRepo(),
            self.sourcesMenu,
            triggered=self.onAddGitHashmarkSource
        )

        self.addIpfsMarksSourceAction = QAction(
            self.icon(),
            iHashmarkSourcesAddLegacyIpfsMarks(),
            self.sourcesMenu,
            triggered=lambda: ensure(self.onAddIpfsMarksSource())
        )

        self.sourcesMenu.addAction(self.syncAction)
        self.sourcesMenu.addSeparator()
        self.sourcesMenu.addAction(self.addGitSourceAction)
        self.sourcesMenu.addSeparator()
        self.sourcesMenu.addAction(self.addIpfsMarksSourceAction)

        self.menu.addMenu(self.sourcesMenu)
        self.menu.addSeparator()
        self.menu.addMenu(self.popularTagsMenu)
        self.menu.addSeparator()
        self.app.hmSynchronizer.syncing.connectTo(self.onSynchronizing)

    async def onShowPopularTags(self):
        self.popularTagsMenu.clear()

        tags = await database.hashmarksPopularTags(limit=20)

        for tag in tags:
            menu = QMenu(tag.name, self.popularTagsMenu)
            menu.setIcon(getIcon('ipfs-logo-128-white.png'))
            menu.menuAction().setData(tag)
            menu.triggered.connect(
                lambda action: ensure(self.linkActivated(action)))
            self.popularTagsMenu.addMenu(menu)

            menu.aboutToShow.connect(
                partialEnsure(self.onShowTagHashmarks, menu))

    async def onFollowTag(self, tagName):
        tag = await database.ipTagGet(tagName)
        if tag:
            tag.follow = True
            await tag.save()

    async def onShowTagHashmarks(self, menu):
        menu.clear()
        menu.setToolTipsVisible(True)
        tag = menu.menuAction().data()

        if 0:
            menu.addAction(self.icon(), 'Follow this tag',
                           lambda: partialEnsure(self.onFollowTag, tag.name))

        hashmarks = await database.hashmarksByTags(
            [tag.name], strict=True, limit=30)

        for hashmark in hashmarks:
            await hashmark._fetch_all()
            menu.addAction(self.makeHashmarkAction(hashmark))

    def onAddGitHashmarkSource(self):
        url = inputTextCustom(title=iHashmarkSourcesAddGitRepo(),
                              label='Git repository URL')
        if url:
            ensure(self.addGitHashmarkSource(url))

    async def addGitHashmarkSource(self, url):
        if url:
            await database.hashmarkSourceAdd(
                database.HashmarkSource.TYPE_GITREPOS,
                url
            )

    async def onAddIpfsMarksSource(self):
        ex = await database.hashmarkSourceSearch(
            type=database.HashmarkSource.TYPE_IPFSMARKS_LEGACY
        )

        if ex:
            return await messageBoxAsync(iHashmarkSourceAlreadyRegistered())

        try:
            await database.hashmarkSourceAdd(
                database.HashmarkSource.TYPE_IPFSMARKS_LEGACY,
                self.app.marksLocal.path,
                name='ipfsmarks'
            )
        except Exception as err:
            log.debug(str(err))

    async def onSynchronizing(self, onoff):
        self.syncAction.setEnabled(not onoff)

    async def onSynchronize(self):
        await self.app.hmSynchronizer.sync()

    async def onMarkAdded(self, hashmark):
        await hashmark._fetch_all()

        if not hashmark.category:
            # Uncategorized, no need then
            return

        menu = self.categoryMenu(hashmark.category.name)
        menu.addAction(self.makeHashmarkAction(hashmark))

        await self.updateIcons()

    async def onMarkDeleted(self, mark):
        await mark.fetch_related('category')

        if mark.category.name in self.cMenus:
            menu = self.cMenus[mark.category.name]

            for action in menu.actions():
                data = action.data()

                if data and data['mark'].url == mark.url:
                    menu.removeAction(action)

            if menu.isEmpty():
                menu.hide()

    async def updateIcons(self):
        for mName, menu in self.cMenus.items():
            await asyncio.sleep(0)

            for action in menu.actions():
                data = action.data()

                if 'iconloaded' not in data and data['iconpath']:
                    ensure(self.loadMarkIcon(action, data['iconpath']))

    def categoryMenu(self, category):
        if category not in self.cMenus:
            self.cMenus[category] = QMenu(category)
            self.cMenus[category].setToolTipsVisible(True)
            self.cMenus[category].triggered.connect(
                lambda action: ensure(self.linkActivated(action)))
            self.cMenus[category].setObjectName('hashmarksMgrMenu')
            self.cMenus[category].setIcon(getIcon('stroke-cube.png'))
            self.menu.addMenu(self.cMenus[category])

        return self.cMenus[category]

    async def updateMenu(self):
        self.hCount = 0
        categories = await database.categoriesNames()

        for category in categories:
            marks = await database.hashmarksSearch(category=category)

            menu = self.categoryMenu(category)

            def exists(path):
                for action in menu.actions():
                    if action.data()['path'] == path:
                        return action

            for hashmark in marks:
                if exists(hashmark.path):
                    continue

                await hashmark._fetch_all()
                menu.addAction(self.makeHashmarkAction(hashmark))
            else:
                menu.hide()

        self.setToolTip(iHashmarksDatabase())

    async def linkActivated(self, action):
        mark = action.data()['mark']

        if mark:
            mark.visitcount += 1
            mark.lastvisited = utcDatetime()
            await mark.save()

            self.hashmarkClicked.emit(mark)


class HashmarksSearchWidgetAction(QWidgetAction):
    pass


class HashmarksSearchLine(QLineEdit):
    """
    The hashmarks search line edit.

    Run the search when Shift + Return is pressed.
    """
    searchRequest = pyqtSignal(str)
    returnNoModifier = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        event.ignore()

    def keyPressEvent(self, event):
        if event.type() == QEvent.KeyPress:
            modifiers = event.modifiers()
            key = event.key()

            if modifiers & Qt.ShiftModifier:
                if key == Qt.Key_Return:
                    searchText = self.text().strip()
                    if searchText:
                        self.searchRequest.emit(searchText)

                    return
            else:
                if event.key() == Qt.Key_Return:
                    self.returnNoModifier.emit()
                    return

        return super().keyPressEvent(event)


class HashmarksSearcher(PopupToolButton, _HashmarksCommon):
    hashmarkClicked = pyqtSignal(Hashmark)

    def __init__(self, iconFile='hashmarks-library.png', parent=None,
                 mode=QToolButton.InstantPopup):
        super(HashmarksSearcher, self).__init__(parent=parent, mode=mode)

        self.app = QApplication.instance()

        self._catalog = {}
        self._sMenus = []
        self.setObjectName('hashmarksSearcher')

        self.setIcon(getIcon(iconFile))
        self.setShortcut(QKeySequence('Ctrl+Alt+h'))

        self.menu.setTitle(iSearchHashmarks())
        self.menu.setIcon(getIcon(iconFile))
        self.menu.setObjectName('hashmarksSearchMenu')
        self.menu.setToolTipsVisible(True)
        self.menu.aboutToShow.connect(self.aboutToShowMenu)
        self.configureMenu()

    @property
    def searchesCount(self):
        return len(self.menu.actions()) - len(self.protectedActions)

    @property
    def protectedActions(self):
        return [self.searchWAction, self.clearAction]

    def isProtectedAction(self, action):
        for pAction in self.protectedActions:
            if action is pAction:
                return True
        return False

    def aboutToShowMenu(self):
        self.searchLine.setFocus(Qt.OtherFocusReason)

    def configureMenu(self):
        self.clearAction = QAction(
            getIcon('clear-all.png'),
            'Clear searches',
            self.menu,
            triggered=self.onClearSearches
        )
        self.clearAction.setEnabled(False)
        self.searchLine = HashmarksSearchLine(self.menu)
        self.searchLine.setObjectName('hLibrarySearch')

        mediumSize = self.fontMetrics().size(0, '*' * (40))
        self.searchLine.setMinimumSize(QSize(mediumSize.width(), 32))
        self.searchLine.setFocusPolicy(Qt.StrongFocus)

        self.searchLine.returnNoModifier.connect(self.onReturnNoShift)
        self.searchLine.searchRequest.connect(self.onSearch)
        self.searchLine.setToolTip(iSearchHashmarksAllAcross())

        self.searchLine.setValidator(
            QRegExpValidator(QRegExp(r"[\w\s@\+\-_./?'\"!#]+")))
        self.searchLine.setMaxLength(96)
        self.searchLine.setClearButtonEnabled(True)

        self.searchWAction = HashmarksSearchWidgetAction(self.menu)
        self.searchWAction.setDefaultWidget(self.searchLine)
        self.menu.addAction(self.searchWAction)
        self.menu.setDefaultAction(self.searchWAction)
        self.menu.addAction(self.clearAction)

    def onReturnNoShift(self):
        QToolTip.showText(self.searchLine.mapToGlobal(
            QPoint(30, self.searchLine.height())),
            iSearchUseShiftReturn(),
            self.searchLine, QRect(0, 0, 0, 0), 1800)

    def onSearch(self, text):
        for action in self.menu.actions():
            if self.isProtectedAction(action):
                continue
            if action.text() == text:
                self.menu.removeAction(action)

        ensure(self.searchInCatalog(text))

    @asyncify
    async def searchInCatalog(self, text):
        from galacteek.core.iptags import ipTagsRFind

        resultsMenu = QMenu(text, self.menu)
        resultsMenu.setToolTipsVisible(True)
        resultsMenu.setObjectName('hashmarksSearchMenu')
        resultsMenu.triggered.connect(
            lambda action: ensure(self.linkActivated(
                action, closeMenu=True)))

        resultsMenu.menuAction().setData({
            'query': text,
            'datecreated': datetime.now()
        })

        showMax = 128
        added = 0

        tags = ipTagsRFind(text)
        if len(tags) > 0:
            hashmarks = await database.hashmarksByTags(
                tags, defaultPlanet=False
            )
        else:
            hashmarks = await database.hashmarksSearch(text)

        for hashmark in hashmarks:
            await asyncio.sleep(0)
            await hashmark._fetch_all()

            resultsMenu.addAction(self.makeHashmarkAction(hashmark))

            if added > showMax:
                break

            added += 1

        if len(resultsMenu.actions()) > 0:
            self.menu.addMenu(resultsMenu)
            resultsMenu.setIcon(getIcon('search-engine.png'))

        self.clearAction.setEnabled(self.searchesCount > 0)
        self.searchLine.clear()

    def onClearSearches(self):
        for action in self.menu.actions():
            if not self.isProtectedAction(action):
                self.menu.removeAction(action)

        self.clearAction.setEnabled(self.searchesCount > 0)

    def register(self, nodeId, ipfsMarks):
        if nodeId in self._catalog.keys():
            del self._catalog[nodeId]

        self._catalog[nodeId] = ipfsMarks

    async def linkActivated(self, action, closeMenu=False):
        mark = action.data()['mark']

        if mark:
            mark.visitcount += 1
            mark.lastvisited = utcDatetime()
            await mark.save()

            self.hashmarkClicked.emit(mark)

            self.searchLine.clear()
            if closeMenu:
                self.menu.hide()


class ImageWidget(QLabel):
    """
    Displays an image stored in IPFS into a QLabel
    """

    def __init__(self, scaleWidth=64, parent=None):
        super(ImageWidget, self).__init__(parent)

        self._imgPath = None
        self._scaleWidth = scaleWidth

    @property
    def imgPath(self):
        return self._imgPath

    @ipfsOp
    async def load(self, ipfsop, path):
        try:
            imgData = await ipfsop.waitFor(
                ipfsop.client.cat(path), 8
            )

            if not imgData:
                raise Exception('Failed to load image')

            img1 = QImage()
            img1.loadFromData(imgData)
            img = img1.scaledToWidth(self._scaleWidth)

            self.setPixmap(QPixmap.fromImage(img))
            self._imgPath = path
            return True
        except Exception:
            return False


class DownloadProgressButton(PopupToolButton):
    downloadProgress = pyqtSignal(int)
    downloadFinished = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, path, stat, parent=None):
        super(DownloadProgressButton, self).__init__(
            icon=getIcon('download.png'),
            parent=parent, mode=QToolButton.InstantPopup)
        self.downloadProgress.connect(self.onProgress)
        self.downloadFinished.connect(self.onFinished)
        self.path = path
        self.stat = stat
        self.readBytes = 0
        self.task = None

        self.menu.addAction(iCancel(), self.onCancel)

    def onCancel(self):
        if self.task:
            try:
                self.task.cancel()
            except:
                pass

            self.cancelled.emit()

    def onProgress(self, read):
        statInfo = StatInfo(self.stat)

        self.readBytes = read
        size = sizeFormat(statInfo.totalSize) if statInfo.valid else \
            iUnknown()

        self.setToolTip('{path} (size: {size}): downloaded {dl}'.format(
            path=self.path,
            size=size,
            dl=sizeFormat(self.readBytes))
        )

    def onFinished(self):
        self.setToolTip('{path}: download finished'.format(path=self.path))


class IconSelector(QComboBox):
    """
    A simple icon selector. The selected icon is injected in the
    repository and a signal with its CID is emitted
    """
    iconSelected = pyqtSignal(str)
    emptyIconSelected = pyqtSignal()

    iconsList = [
        ':/share/icons/distributed.png',
        ':/share/icons/atom.png',
        ':/share/icons/atom-rpg.png',
        ':/share/icons/cerebro.png',
        ':/share/icons/ipfs-cube-64.png',
        ':/share/icons/ipfs-logo-128-white.png',
        ':/share/icons/code-fork.png',
        ':/share/icons/cube-blue.png',
        ':/share/icons/cube-orange.png',
        ':/share/icons/cubehouse.png',
        ':/share/icons/fragments.png',
        ':/share/icons/go-home.png',
        ':/share/icons/hotspot.png',
        ':/share/icons/ipld-logo.png',
        ':/share/icons/pyramid-aqua.png',
        ':/share/icons/pyramid-stack.png',
        ':/share/icons/multimedia.png',
        ':/share/icons/folder-documents.png',
        ':/share/icons/folder-pictures.png',
        ':/share/icons/orbitdb.png',
        ':/share/icons/pyramid-hierarchy.png',
        ':/share/icons/sweethome.png',
        ':/share/icons/stroke-code.png',
        ':/share/icons/web-devel.png',
        ':/share/icons/mimetypes/image-x-generic.png',
        ':/share/icons/mimetypes/application-pdf.png',
        ':/share/icons/mimetypes/application-epub+zip.png',
        ':/share/icons/mimetypes/application-x-directory.png',
        ':/share/icons/mimetypes/text-html.png',
        'qta:ei.book',
        'qta:ei.bulb',
        'qta:ei.certificate',
        'qta:ei.cog',
        'qta:ei.fire',
        'qta:ei.fork',
        'qta:ei.github-text',
        'qta:ei.github',
        'qta:ei.globe',
        'qta:ei.heart',
        'qta:ei.livejournal',
        'qta:ei.mic',
        'qta:ei.network',
        'qta:ei.picture',
        'qta:ei.podcast',
        'qta:ei.qrcode',
        'qta:ei.upload',
        'qta:ei.video',
        'qta:ei.video-alt',
        'qta:ei.video-chat',
        'qta:fa.code',
        'qta:fa.cube',
        'qta:fa.file-audio-o',
        'qta:fa.file-image-o',
        'qta:fa.file-movie-o',
        'qta:fa.file-pdf-o',
        'qta:fa.github',
        'qta:fa.linux',
        'qta:fa.paragraph',
        'qta:fa.resistance',
        'qta:fa.star-half-full',
        'qta:fa.wikipedia',
        'qta:fa.youtube',
        'qta:fa5.file-pdf',
        'qta:fa5b.canadian-maple-leaf',
        'qta:fa5b.galactic-republic',
        'qta:fa5b.gitraken',
        'qta:fa5b.grav',
        'qta:fa5s.dice-d6'
    ]

    def __init__(self, parent=None, offline=False, allowEmpty=False):
        super(IconSelector, self).__init__(parent)

        self.app = QApplication.instance()
        self.allowEmpty = allowEmpty
        self.offline = offline
        self.iconCid = None

        if self.app.system == 'Linux':
            self.setIconSize(QSize(64, 64))

        if allowEmpty is True:
            self.addItem('No icon')

        for iconP in self.iconsList:
            icon = getIcon(iconP)
            if icon:
                self.addItem(icon, '', QVariant(iconP))

        self.view = QListView(self)
        self.setView(self.view)
        self.currentIndexChanged.connect(self.onIndexChanged)

        if allowEmpty is False:
            self.injectCurrent()

    def injectCurrent(self):
        self.injectIconFromIndex(self.currentIndex())

    def injectIconFromIndex(self, idx):
        iconPath = self.itemData(idx)
        if iconPath:
            if iconPath.startswith('qta:'):
                ensure(self.injectQaIcon(idx, iconPath))
            else:
                ensure(self.injectQrcIcon(iconPath))

    def onIndexChanged(self, idx):
        if self.allowEmpty and idx == 0:
            self.emptyIconSelected.emit()
        else:
            self.injectIconFromIndex(idx)

    @ipfsOp
    async def injectQaIcon(self, ipfsop, idx, iconPath):
        """
        Inject a QtAwesome font in the IPFS repository
        (PNG, fixed-size 128x128)
        """

        icon = self.itemIcon(idx)

        try:
            size = QSize(128, 128)
            pixmap = icon.pixmap(size)
            array = QByteArray()
            buffer = QBuffer(array)
            buffer.open(QIODevice.WriteOnly)
            pixmap.save(buffer, 'png')
            buffer.close()
        except Exception as err:
            log.debug('QtAwesome inject error: {}'.format(str(err)))
        else:
            entry = await ipfsop.addBytes(array.data(), offline=self.offline)
            if entry:
                self.iconCid = entry['Hash']
                self.iconSelected.emit(self.iconCid)
                self.setToolTip(self.iconCid)
                return True

    @ipfsOp
    async def injectQrcIcon(self, op, iconPath):
        _file = QFile(iconPath)
        if _file.exists():
            if not _file.open(QIODevice.ReadOnly):
                return False

            data = _file.readAll().data()

            entry = await op.addBytes(data, offline=self.offline)
            if entry:
                self.iconCid = entry['Hash']
                self.iconSelected.emit(self.iconCid)
                self.setToolTip(self.iconCid)
                return True


class IPFSWebView(QWebEngineView):
    def __init__(self, webProfile=None, parent=None):
        super(IPFSWebView, self).__init__(parent=parent)

        self.app = QApplication.instance()
        self.webProfile = webProfile if webProfile else \
            self.app.webProfiles['ipfs']
        self.setPage(QWebEnginePage(self.webProfile, self))

        self.setMinimumSize(QSize(
            self.app.desktopGeometry.width() / 8,
            self.app.desktopGeometry.height() / 8
        ))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


class MarkdownView(IPFSWebView):
    pass


class MarkdownTextEdit(QPlainTextEdit):
    """
    Custom QTextEdit widget for markdown editing

    Drag-and-dropping an IPFS object to this widget will insert
    a markdown link in the editor
    """

    redrawPreview = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('markdownTextEdit')

    def dragEnterEvent(self, event):
        event.accept()

    async def handleObjectDrop(self, path, urlType='fullpath'):
        path = IPFSPath(path, autoCidConv=True)

        if path.valid:
            name = path.basename

            if urlType == 'fullpath':
                url = path.ipfsUrl
            elif urlType == 'fullpathgw':
                url = path.publicGwUrl
            else:
                # unknown
                return

            mType = await detectMimeType(path.objPath)

            if mType and mType.isImage:
                # Fetch the image, and set width/height style
                # using attr_list (markdown extension)

                image = await getImageFromIpfs(path.objPath)

                if image:
                    style = '{: ' + \
                        'style="width:{width}px; height:{height}px"'.format(
                            width=image.width(),
                            height=image.height()
                        ) + ' }'

                    # Image link
                    self.insertPlainText(
                        "[![{name}]({url}){istyle}]({url})\n".format(
                            name=name,
                            url=url,
                            istyle=style
                        )
                    )
            else:
                # Standard link
                self.insertPlainText(
                    "[{name}]({url})\n".format(
                        name=name,
                        url=url
                    )
                )
            return True

        return False

    def dropEvent(self, event):
        mimeData = event.mimeData()

        if mimeData is None:
            event.ignore()
            return

        if mimeData.hasUrls():
            for url in mimeData.urls():
                if not url.isValid():
                    continue

                self.handleObjectDrop(url.toString())

            event.ignore()
            self.redrawPreview.emit()

        elif mimeData.hasText():
            if self.handleObjectDrop(mimeData.text()):
                event.ignore()
                self.redrawPreview.emit()
        else:
            event.accept()

    def insertFromMimeData(self, mimeData):
        self.insertPlainText(mimeData.text())

    async def _fromMimeData(self, mimeData):
        if mimeData.hasText():
            if await self.handleObjectDrop(mimeData.text()):
                self.redrawPreview.emit()
            else:
                self.insertPlainText(mimeData.text())

    def contextMenuEvent(self, event):
        app = QApplication.instance()
        clipMgr = app.mainWindow.clipboardManager
        menu = self.createStandardContextMenu()

        def onPaste():
            clipItem = clipMgr.tracker.current
            if clipItem:
                ensure(self.onLinkClipboardItem(clipItem, 'fullpath'))

        for action in menu.actions():
            if action.text().startswith('&Paste'):
                menu.removeAction(action)
                break

        pAction = QAction('&Paste from clipboard', self, triggered=onPaste)
        menu.addSeparator()
        menu.addAction(pAction)

        if clipMgr.itemsStack.count() > 0:
            itemsMenu = QMenu(
                'Link clipboard item',
                menu
            )
            itemsMenu.setIcon(getIcon('clipboard.png'))
            itemsMenu.setToolTipsVisible(True)

            for idx, clipItem in clipMgr.itemsStack.items(count=20):
                itMenu = QMenu(clipItem.pathShort, itemsMenu)
                itMenu.setToolTipsVisible(True)
                itMenu.setToolTip(clipItem.path)

                icon = clipItem.mimeIcon if clipItem.mimeIcon else \
                    getMimeIcon('unknown')

                itMenu.setIcon(icon)

                itMenu.addAction(
                    icon,
                    iIPFSUrlTypeNative(),
                    partialEnsure(
                        self.onLinkClipboardItem,
                        clipItem,
                        'fullpath'
                    )
                ).setToolTip(clipItem.path)

                itMenu.addAction(
                    icon,
                    iIPFSUrlTypeHttpGateway(),
                    partialEnsure(
                        self.onLinkClipboardItem,
                        clipItem,
                        'fullpathgw'
                    )
                ).setToolTip(clipItem.path)

                itemsMenu.addMenu(itMenu)

            menu.addSeparator()
            menu.addMenu(itemsMenu)

        menu.exec(event.globalPos())

    async def onLinkClipboardItem(self, clipItem, urlType):
        if await self.handleObjectDrop(clipItem.path, urlType=urlType):
            self.redrawPreview.emit()


class MarkdownInputWidget(QWidget):
    """
    General purpose markdown input editor, with (almost) live
    preview in a qtwebengine view

    It supports the 'dweb' URL scheme, so when you type something
    like ![img](dweb:/pathtoimage) the image should appear in
    the preview widget
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = QApplication.instance()
        self.setObjectName('markdownInputWidget')

        self.markdownDocButton = QToolButton()
        self.markdownDocButton.setIcon(getIcon('qta:fa5b.markdown'))
        self.markdownDocButton.setToolTip(
            'Have you completely lost your Markdown ?')

        self.markdownDocButton.clicked.connect(self.onMarkdownHelp)
        helpLayout = QHBoxLayout()
        labelsLayout = QHBoxLayout()
        labelsLayout.addWidget(self.markdownDocButton)
        labelsLayout.addWidget(QLabel('Markdown input'))
        labelsLayout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        labelsLayout.addWidget(QLabel('Preview'))

        helpLayout.addWidget(self.markdownDocButton)
        helpLayout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.textEditUser = MarkdownTextEdit(self)
        self.textEditUser.redrawPreview.connect(self.onTimerOut)
        self.textEditUser.setAcceptDrops(True)
        self.textEditUser.textChanged.connect(self.onEdited)
        self.textEditMarkdown = MarkdownView(parent=self)

        self.updateTimeoutMs = 500
        self.updateTimer = QTimer()
        self.updateTimer.timeout.connect(self.onTimerOut)

        mainLayout = QVBoxLayout()
        mainLayout.setContentsMargins(30, 30, 30, 30)
        editLayout = QHBoxLayout()
        editLayout.addWidget(self.textEditUser)
        editLayout.addWidget(self.textEditMarkdown)

        mainLayout.addLayout(labelsLayout)
        mainLayout.addLayout(editLayout)

        self.setLayout(mainLayout)
        self.setMinSize()

    def onMarkdownHelp(self):
        ref = self.app.ipfsCtx.resources.get('markdown-reference')
        if ref:
            self.app.mainWindow.addBrowserTab().browseIpfsHash(
                ref['Hash']
            )

    def setMinSize(self):
        self.textEditUser.setMinimumSize(QSize(
            self.app.desktopGeometry.width() / 3,
            self.app.desktopGeometry.height() / 2)
        )
        self.textEditMarkdown.setMinimumSize(QSize(
            self.app.desktopGeometry.width() / 3,
            self.app.desktopGeometry.height() / 2)
        )

    def markdownText(self):
        return self.textEditUser.toPlainText()

    def onEdited(self):
        if self.updateTimer.isActive():
            self.updateTimer.stop()

        self.updateTimer.start(self.updateTimeoutMs)

    def onTimerOut(self):
        textData = self.textEditUser.toPlainText()
        try:
            html = markitdown(textData)
            self.textEditMarkdown.setHtml(html)
        except Exception:
            pass

        self.updateTimer.stop()


class AtomFeedsToolbarButton(QToolButton):
    subscribeResult = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super(AtomFeedsToolbarButton, self).__init__(parent=parent)
        self.app = QApplication.instance()
        self.model = self.app.modelAtomFeeds
        self.model.root.tracker.unreadCountChanged.connect(
            self.unreadEntriesCountChanged)
        self.setIcon(getIcon('atom-feed.png'))
        self.subscribeResult.connect(self.onSubResult)

        self.setToolTip('Atom Feeds reader')

    def unreadEntriesCountChanged(self, count):
        self.setToolTip('Atom Feeds reader: {count} unread entries'.format(
            count=count))

    def onSubResult(self, url, result):
        if result == 1:
            messageBox('This Atom feed is already registered', title=url)
        elif result == 2:
            messageBox('Error while subscribing to Atom feed', title=url)
        elif result == 3:
            messageBox('Subscribe OK!', title=url)

    async def atomFeedSubscribe(self, url):
        from galacteek.dweb.atom import AtomFeedExistsError
        try:
            await self.app.sqliteDb.feeds.follow(url)
        except AtomFeedExistsError:
            self.subscribeResult.emit(url, 1)
        except Exception as err:
            log.debug(str(err))
            self.subscribeResult.emit(url, 2)
        else:
            self.subscribeResult.emit(url, 3)


class PageSourceWidget(QTextBrowser):
    def __init__(self, parent):
        super(PageSourceWidget, self).__init__(parent)

        self.app = QApplication.instance()
        self.setAcceptRichText(True)
        self.setLineWrapMode(QTextEdit.WidgetWidth)

    async def showSource(self, sourceText):
        formatter = HtmlFormatter()
        cssDefs = formatter.get_style_defs()

        lexer = get_lexer_by_name('html')

        self.document().setPlainText('Loading ...')
        try:
            high = await self.app.loop.run_in_executor(
                self.app.executor, highlight,
                sourceText, lexer, formatter)

            self.document().setDefaultStyleSheet(cssDefs)
            self.document().setHtml(high)
        except:
            self.document().setPlainText('Could not load source')

        self.moveCursor(QTextCursor.Start)


class AnimatedButton(QPushButton):
    """
    Animated button.
    """

    def __init__(self, clip, ignoreFrameEvery=1, parent=None):
        super().__init__(parent)

        self.clip = clip
        self.clip.finished.connect(self.clip.start)
        self.clip.frameChanged.connect(self.onFrameChanged)
        self.ignoreFrameEvery = ignoreFrameEvery

    def startClip(self):
        if not self.clip.playing():
            self.clip.start()

    def onFrameChanged(self, fNum):
        if divmod(fNum, self.ignoreFrameEvery)[1] == 0:
            self.setIcon(self.clip.createIcon())


class AnimatedLabel(QLabel):
    """
    Animated label.
    """

    animationClicked = pyqtSignal()
    hovered = pyqtSignal(bool)

    def __init__(self, clip, loop=True, parent=None):
        super().__init__(parent)

        self.setMouseTracking(True)

        self.clip = clip

        if self.clip.isValid():
            self.setMovie(self.clip)

        if loop:
            self.clip.finished.connect(self.clip.start)

    def mousePressEvent(self, event):
        self.animationClicked.emit()

    def startClip(self):
        if not self.clip.playing():
            self.clip.start()

    def stopClip(self):
        self.clip.stop()

    def enterEvent(self, event):
        self.hovered.emit(True)
        super(AnimatedLabel, self).enterEvent(event)

    def leaveEvent(self, event):
        self.hovered.emit(False)
        super(AnimatedLabel, self).enterEvent(event)
