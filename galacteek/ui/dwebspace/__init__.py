import rule_engine

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QTabWidget
from PyQt5.QtWidgets import QTabBar
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QToolBar
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QSpacerItem

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QEvent
from PyQt5.QtCore import QSize

from galacteek.ui.peers import PeersManager
from galacteek import partialEnsure
from galacteek import ensure

from galacteek.ui import files
from galacteek.ui import ipfssearch
from galacteek.ui import textedit
from galacteek.ui import mediaplayer
from galacteek.ui import pin
from galacteek.ui import seeds

from galacteek.ui.helpers import getIcon
from galacteek.ui.helpers import getPlanetIcon
from galacteek.ui.helpers import playSound
from galacteek.ui.helpers import questionBoxAsync

from galacteek.ui.feeds import AtomFeedsViewTab
from galacteek.ui.feeds import AtomFeedsView
from galacteek.ui.i18n import *


class TabWidgetKeyFilter(QObject):
    nextPressed = pyqtSignal()
    closePressed = pyqtSignal()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            modifiers = event.modifiers()

            key = event.key()
            if modifiers & Qt.ControlModifier:
                if key == Qt.Key_J:
                    self.nextPressed.emit()
                    return True

                if key == Qt.Key_W:
                    self.closePressed.emit()
        return False


class MainTabBar(QTabBar):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.setAcceptDrops(True)
        self.setObjectName('wsTabBar')
        self.tabWidget = parent
        self.setIconSize(QSize(24, 24))

    def dragEnterEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        tabIdx = self.tabAt(event.pos())
        tab = self.tabWidget.widget(tabIdx)

        if tab:
            self.tabWidget.tabDropProcessEvent(tab, event)


class MainTabWidget(QTabWidget):
    onTabInserted = pyqtSignal(int)
    onTabRemoved = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setTabBar(MainTabBar(self))
        self.setTabsClosable(True)
        self.setElideMode(Qt.ElideMiddle)
        self.setUsesScrollButtons(True)
        self.setObjectName('wsTabWidget')
        self.setAcceptDrops(True)

        tabKeyFilter = TabWidgetKeyFilter(self)
        tabKeyFilter.nextPressed.connect(self.cycleTabs)
        tabKeyFilter.closePressed.connect(self.closeCurrentTab)

    def tabDropProcessEvent(self, tab, event):
        tab.tabDropEvent(event)

    def removeTabFromWidget(self, w):
        idx = self.tabWidget.indexOf(w)
        if idx:
            self.tabWidget.removeTab(idx)

    def closeCurrentTab(self):
        self.tabCloseRequested.emit(self.currentIndex())

    def cycleTabs(self):
        curIndex = self.currentIndex()
        if curIndex + 1 < self.count():
            self.setCurrentIndex(curIndex + 1)
        else:
            self.setCurrentIndex(0)

    def tabInserted(self, index):
        self.onTabInserted.emit(index)
        super().tabInserted(index)

    def tabRemoved(self, index):
        self.onTabRemoved.emit(index)
        super().tabRemoved(index)


class ToolBarActionsContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        hLayout = QHBoxLayout(self)
        self.setLayout(hLayout)

        self.toolBar = QToolBar(self)
        self.toolBar.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        hLayout.addItem(
            QSpacerItem(20, 10, QSizePolicy.Maximum, QSizePolicy.Expanding))
        hLayout.addWidget(self.toolBar)


WS_MAIN = 'main'
WS_PEERS = 'peers'
WS_FILES = 'files'
WS_MULTIMEDIA = 'multimedia'
WS_EDIT = 'edit'
WS_SEARCH = 'search'
WS_MISC = 'misc'


class BaseWorkspace(QWidget):
    def __init__(self, stack,
                 name,
                 description=None,
                 section='default',
                 icon=None,
                 acceptsDrops=False):
        super().__init__(parent=stack)

        self.acceptsDrops = acceptsDrops

        self.wsName = name
        self.wsDescription = description
        self.wsSection = section
        self.wsAttached = False
        self.defaultAction = None

    def setupWorkspace(self):
        pass

    async def loadDapps(self):
        pass

    async def handleObjectDrop(self, ipfsPath):
        pass


class TabbedWorkspace(BaseWorkspace):
    def __init__(self, stack,
                 name,
                 description=None,
                 section='default',
                 icon=None,
                 acceptsDrops=False):
        super(TabbedWorkspace, self).__init__(
            stack, name, description=description,
            section=section, icon=icon,
            acceptsDrops=acceptsDrops
        )

        self.wsTagRules = []
        self.wsActions = {}

        self.app = QApplication.instance()
        self.stack = stack
        self.wLayout = QVBoxLayout(self)
        self.setLayout(self.wLayout)

        self.toolBarCtrl = QToolBar()
        self.toolBarActions = QToolBar()
        self.toolBarActions.setObjectName('wsActionsToolBar')

        self.wsIcon = icon if icon else getIcon('galacteek.png')

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def wsToolTip(self):
        return self.wsDescription

    def wsTabs(self):
        for tidx in range(self.tabWidget.count()):
            yield tidx, self.tabWidget.widget(tidx)

    def wsFindTabWithName(self, name):
        for idx in range(0, self.tabWidget.count()):
            tName = self.tabWidget.tabText(idx)

            if tName.strip() == name.strip():
                return self.tabWidget.widget(idx)

    def wsFindTabWithId(self, id):
        for tidx, tab in self.wsTabs():
            if tab and tab.ctx.tabIdent == id:
                return tab

    def empty(self):
        return self.tabWidget.count() == 0

    def workspaceIdx(self):
        return self.stack.indexOf(self)

    def setupWorkspace(self):
        # Workspace's tab widget and toolbars
        self.tabWidget = MainTabWidget(self)

        self.wLayout.addWidget(self.tabWidget)

        self.tabWidget.setElideMode(Qt.ElideMiddle)
        self.tabWidget.setUsesScrollButtons(True)
        self.tabWidget.onTabRemoved.connect(
            partialEnsure(self.wsTabRemoved))
        self.tabWidget.currentChanged.connect(
            partialEnsure(self.wsTabChanged))
        self.tabWidget.tabCloseRequested.connect(
            partialEnsure(self.onTabCloseRequest))

        if self.app.system != 'Darwin':
            self.tabWidget.setDocumentMode(True)

        # Set the corner widgets
        # Workspace actions on the left, the right toolbar is unused for now

        self.setCornerRight(self.toolBarCtrl)
        self.setCornerLeft(self.toolBarActions)

    def setCornerLeft(self, pButton):
        self.tabWidget.setCornerWidget(pButton, Qt.TopLeftCorner)

    def setCornerRight(self, nButton):
        self.tabWidget.setCornerWidget(nButton, Qt.TopRightCorner)

    def previousWorkspace(self):
        return self.stack.previousWorkspace(self)

    def nextWorkspace(self):
        return self.stack.nextWorkspace(self)

    def wsRegisterTab(self, tab, name, icon=None, current=False,
                      tooltip=None):
        if icon:
            idx = self.tabWidget.addTab(tab, icon, name)
        else:
            idx = self.tabWidget.addTab(tab, name)

        tab.workspaceAttach(self)

        if current is True:
            self.tabWidget.setCurrentWidget(tab)
            tab.setFocus(Qt.OtherFocusReason)

        if tooltip and idx:
            self.tabWidget.setTabToolTip(idx, tooltip)

    async def workspaceSwitched(self):
        await self.triggerDefaultActionIfEmpty()

    async def wsTabChanged(self, tabidx):
        tab = self.tabWidget.widget(tabidx)
        if tab:
            await tab.onTabChanged()

    async def wsTabRemoved(self, tabidx):
        await self.triggerDefaultActionIfEmpty()

    async def triggerDefaultActionIfEmpty(self):
        if self.empty() and self.defaultAction:
            self.defaultAction.trigger()

    def wsAddCustomAction(self, actionName: str, icon, name,
                          func, default=False):
        action = self.toolBarActions.addAction(
            icon, name, func
        )
        self.wsActions[actionName] = action

        if default is True and not self.defaultAction:
            self.defaultAction = action

        return action

    def wsAddAction(self, action: QAction, default=False):
        self.toolBarActions.addAction(action)

        if default is True and not self.defaultAction:
            self.defaultAction = action

        if len(list(self.toolBarActions.actions())) == 1 and \
                not self.defaultAction:
            # Only one action yet, make it the default
            self.defaultAction = action

    def wsAddWidget(self, widget):
        self.toolBarActions.addWidget(widget)

    async def onTabCloseRequest(self, idx):
        tab = self.tabWidget.widget(idx)

        if tab is None:
            # TODO
            return

        if tab.sticky is True:
            # Sticky tab
            return

        if await tab.onClose() is True:
            self.tabWidget.removeTab(idx)
            del tab

    def wsSwitch(self, soundNotify=False):
        self.stack.setCurrentIndex(self.workspaceIdx())

        if soundNotify and 0:
            playSound('wsswitch.wav')

    def wsTagRulesMatchesHashmark(self, hashmark):
        tags = [
            {
                'tag': tag.name
            } for tag in hashmark.iptags
        ]

        for rule in self.wsTagRules:
            res = list(rule.filter(tags))
            if len(res) > 0:
                return True

        return False


class PlanetWorkspace(TabbedWorkspace):
    def __init__(self, stack,
                 planetName,
                 description=None,
                 icon=None):
        super().__init__(
            stack,
            f'@{planetName}',
            description=description,
            icon=getPlanetIcon(planetName.lower())
        )

        self._planet = planetName

        self.wsTagRules.append(rule_engine.Rule(
            f'tag =~ "@{planetName}#.*"'
        ))

    @property
    def planet(self):
        return self._planet

    def wsToolTip(self):
        return f'Planet workspace: {self.planet}'

    async def loadDapps(self):
        if self.app.cmdArgs.enablequest and 0:
            await self.loadQuestService()

    async def loadQuestService(self):
        from galacteek.dweb.quest import loadQuestService
        self.qView, self.qPage = await loadQuestService()


class WorkspaceCore(TabbedWorkspace):
    def __init__(self, stack):
        super().__init__(stack, WS_MAIN, icon=getIcon('atom.png'),
                         description='Main')


class WorkspaceFiles(TabbedWorkspace):
    def __init__(self, stack):
        super().__init__(stack, WS_FILES, icon=getIcon('folder-open.png'),
                         description='Files')

    def setupWorkspace(self):
        super().setupWorkspace()

        fileManager = self.app.mainWindow.fileManagerWidget

        self.fileManagerTab = files.FileManagerTab(
            self.app.mainWindow,
            fileManager=fileManager
        )

        self.seedsTab = seeds.SeedsTrackerTab(self.app.mainWindow)

        icon = getIcon('folder-open.png')

        self.wsRegisterTab(self.fileManagerTab, iFileManager(), icon)
        self.wsRegisterTab(self.seedsTab, iFileSharing(),
                           getIcon('fileshare.png'))

        self.wsAddAction(fileManager.addFilesAction)
        self.wsAddAction(fileManager.addDirectoryAction)
        self.wsAddAction(fileManager.newSeedAction)

        self.actionGc = self.wsAddCustomAction(
            'gc', getIcon('clear-all.png'),
            iGarbageCollectRun(),
            partialEnsure(self.onRunGC)
        )

    async def seedsSetup(self):
        await self.seedsTab.loadSeeds()

    async def onRunGC(self):
        tab = self.wsFindTabWithId('gcrunner')

        if not tab and await questionBoxAsync(iGarbageCollector(),
                                              iGarbageCollectRunAsk()):

            gcRunnerTab = files.GCRunnerTab(self.app.mainWindow)
            gcRunnerTab.gcClosed.connectTo(self.onGcFinished)

            self.wsRegisterTab(gcRunnerTab, iGarbageCollector(),
                               self.actionGc.icon(), current=True)
            self.actionGc.setEnabled(False)
            ensure(gcRunnerTab.run())

    async def onGcFinished(self):
        self.actionGc.setEnabled(True)

    async def workspaceSwitched(self):
        await super().workspaceSwitched()

        self.fileManagerTab.fileManager.updateTree()


class WorkspaceMultimedia(TabbedWorkspace):
    def __init__(self, stack):
        super().__init__(stack, WS_MULTIMEDIA, icon=getIcon('multimedia.png'),
                         description='Multimedia',
                         acceptsDrops=True)

    def setupWorkspace(self):
        super().setupWorkspace()

        self.mpAction = self.wsAddCustomAction(
            'mplayer', self.wsIcon,
            iMediaPlayer(),
            self.onAddMplayerTab, default=True)

    def mPlayerTab(self):
        tab = self.wsFindTabWithName(iMediaPlayer())
        if tab:
            return tab
        else:
            tab = mediaplayer.MediaPlayerTab(self.app.mainWindow)

            if tab.playerAvailable():
                self.wsRegisterTab(
                    tab, self.mpAction.text(), icon=self.wsIcon,
                    current=True)
                return tab

    def onAddMplayerTab(self):
        return self.mPlayerTab()

    async def handleObjectDrop(self, ipfsPath):
        tab = self.mPlayerTab()
        tab.queueFromPath(ipfsPath.objPath)


class WorkspaceSearch(TabbedWorkspace):
    def __init__(self, stack):
        super().__init__(stack, WS_SEARCH, icon=getIcon('search-engine.png'),
                         description='Search')

    def setupWorkspace(self):
        super().setupWorkspace()

        self.wsAddCustomAction('search', self.wsIcon, iIpfsSearch(),
                               self.onAddSearchTab, default=True)

    def onAddSearchTab(self):
        tab = ipfssearch.IPFSSearchTab(self.app.mainWindow)
        self.wsRegisterTab(tab, iIpfsSearch(), current=True,
                           icon=self.wsIcon)
        tab.view.browser.setFocus(Qt.OtherFocusReason)


class WorkspaceEdition(TabbedWorkspace):
    def __init__(self, stack):
        super().__init__(stack, WS_EDIT, icon=getIcon('blog.png'),
                         description='Edition')

    def setupWorkspace(self):
        super().setupWorkspace()

        self.actionHelp = self.wsAddCustomAction(
            'help', getIcon('help.png'),
            iHelp(), self.onHelpEditing)

        self.actionMarkdownHelp = self.wsAddCustomAction(
            'help', getIcon('qta:fa5b.markdown'),
            'Have you completely lost your Markdown ?',
            self.onHelpMarkdown)

        self.actionPostBlog = self.wsAddCustomAction(
            'blogpost', getIcon('blog.png'),
            iNewBlogPost(), self.onAddBlogPost, default=True)

        self.actionTextEdit = self.wsAddCustomAction(
            'textedit', getIcon('text-editor.png'),
            iTextEditor(), self.onAddTextEditorTab)

    def onHelpEditing(self):
        self.app.manuals.browseManualPage('editing.html')

    def onHelpMarkdown(self):
        self.app.manuals.browseManualPage('markdown.html')

        if 0:
            ref = self.app.ipfsCtx.resources.get('markdown-reference')
            if ref:
                self.app.mainWindow.addBrowserTab().browseIpfsHash(
                    ref['Hash']
                )

    def onAddTextEditorTab(self):
        tab = textedit.TextEditorTab(editing=True, parent=self)
        self.wsRegisterTab(
            tab, iTextEditor(), current=True,
            icon=self.actionTextEdit.icon())

    def onAddBlogPost(self):
        from galacteek.ui.userwebsite import WebsiteAddPostTab

        tab = WebsiteAddPostTab(self.app.mainWindow)
        self.wsRegisterTab(
            tab, iNewBlogPost(), current=True,
            icon=self.actionPostBlog.icon())


class WorkspacePeers(TabbedWorkspace):
    def __init__(self, stack):
        super().__init__(stack, WS_PEERS, icon=getIcon('peers.png'),
                         description='Network')

    def setupWorkspace(self):
        from galacteek.ui import chat

        super().setupWorkspace()

        pMgrTab = PeersManager(self.app.mainWindow, self.app.peersTracker)

        # Chat center button
        self.chatCenterButton = chat.ChatCenterButton(
            parent=self.toolBarActions)

        self.wsRegisterTab(
            pMgrTab, iPeers(),
            icon=getIcon('peers.png'))

        self.app.mainWindow.atomButton.clicked.connect(self.onShowAtomFeeds)
        self.atomFeedsViewWidget = AtomFeedsView(self.app.modelAtomFeeds)

        self.wsAddWidget(self.app.mainWindow.atomButton)
        self.wsAddWidget(self.chatCenterButton)

    def onShowAtomFeeds(self):
        name = iAtomFeeds()

        tab = self.wsFindTabWithName(name)
        if tab:
            return self.tabWidget.setCurrentWidget(tab)

        tab = AtomFeedsViewTab(self, view=self.atomFeedsViewWidget)
        self.wsRegisterTab(tab, name,
                           getIcon('atom-feed.png'), current=True)

    async def chatJoinDefault(self):
        chanWidget = await self.chatCenterButton.chans.joinChannel(
            '#galacteek', chanSticky=False)

        self.wsRegisterTab(
            chanWidget,
            '#galacteek',
            icon=getIcon('qta:mdi.chat-outline'),
            current=False
        )


class WorkspaceMisc(TabbedWorkspace):
    def __init__(self, stack):
        super().__init__(stack, WS_MISC, icon=getIcon('settings.png'),
                         description='Misc')

    def setupWorkspace(self):
        super().setupWorkspace()

        self.pinStatusTab = pin.PinStatusWidget(
            self.app.mainWindow, sticky=True)

        self.wsRegisterTab(
            self.pinStatusTab, iPinningStatus(),
            icon=getIcon('pin-zoom.png'))
