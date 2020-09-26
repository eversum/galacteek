import functools

from logbook import Handler
from logbook import StringFormatterHandlerMixin

from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QToolBar
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QActionGroup
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QStackedWidget
from PyQt5.QtWidgets import QToolTip

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import QDateTime
from PyQt5.QtCore import QSize
from PyQt5.QtCore import QPoint

from PyQt5.Qt import QSizePolicy

from PyQt5.QtGui import QKeySequence
from PyQt5.QtGui import QTextCursor
from PyQt5.QtGui import QTextDocument

from PyQt5 import QtWebEngineWidgets

from galacteek import GALACTEEK_NAME
from galacteek import ensure
from galacteek import partialEnsure
from galacteek import log
from galacteek import database
from galacteek.core.glogger import loggerMain
from galacteek.core.glogger import loggerUser
from galacteek.core.glogger import easyFormatString
from galacteek.core.asynclib import asyncify
from galacteek.ipfs.wrappers import *
from galacteek.ipfs.ipfsops import *
from galacteek.ipfs.cidhelpers import IPFSPath

from galacteek.core.modelhelpers import *

from . import ui_ipfsinfos

from . import userwebsite
from . import browser
from . import files
from . import keys
from . import settings
from . import orbital
from . import textedit
from . import unixfs
from . import ipfssearch
from . import eventlog

from .dids import DIDExplorer
from .clips import RotatingCubeClipSimple
from .clips import RotatingCubeRedFlash140d
from .eth import EthereumStatusButton
from .textedit import TextEditorTab
from .iprofile import ProfileEditDialog
from .iprofile import ProfileButton
from .peers import PeersServiceSearchDock
from .pubsub import PubsubSnifferWidget
from .pyramids import MultihashPyramidsToolBar
from .quickaccess import QuickAccessToolBar
from .daemonstats import BandwidthGraphView
from .daemonstats import PeersCountGraphView
from .camera import CameraController
from .helpers import *
from .widgets import AtomFeedsToolbarButton
from .widgets import PopupToolButton
from .widgets import HashmarkMgrButton
from .widgets import HashmarksSearcher
from .widgets import AnimatedLabel
from .widgets import URLDragAndDropProcessor
from .dialogs import *
from ..appsettings import *
from .i18n import *

from .dwebspace import *

from .clipboard import ClipboardManager
from .clipboard import ClipboardItemsStack


def iPinningItemStatus(pinPath, pinProgress):
    return QCoreApplication.translate(
        'GalacteekWindow',
        '\nPath: {0}, nodes processed: {1}').format(pinPath, pinProgress)


def iAbout():
    from galacteek import __version__
    return QCoreApplication.translate('GalacteekWindow', '''
        <p align='center'>
        <img src=':/share/icons/galacteek.png' />
        </p>

        <p>
        <b>galacteek</b> is a multi-platform Qt5-based browser
        for the distributed web
        </p>
        <br/>
        <p>Contact:
            <a href="mailto: galacteek@protonmail.com">
                galacteek@protonmail.com
            </a>
        </p>
        <p>Authors: see
        <a href="https://github.com/pinnaculum/galacteek/blob/master/AUTHORS.rst">
            AUTHORS.rst
        </a>
        </p>
        <p>galacteek version {0}</p>''').format(__version__)  # noqa


class UserLogsWindow(QMainWindow):
    hidden = pyqtSignal()

    def __init__(self):
        super(UserLogsWindow, self).__init__()
        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self.toolbar)

        self.logsBrowser = QTextEdit(self)
        self.logsBrowser.setReadOnly(True)
        self.logsBrowser.setObjectName('logsTextWidget')
        self.logsBrowser.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.searchBack = QPushButton('Search backward')
        self.searchBack.clicked.connect(self.onSearchBack)
        self.searchFor = QPushButton('Search forward')
        self.searchFor.clicked.connect(self.onSearchForward)

        self.logsSearcher = QLineEdit(self)
        self.logsSearcher.setClearButtonEnabled(True)
        self.toolbar.addWidget(self.logsSearcher)
        self.toolbar.addWidget(self.searchBack)
        self.toolbar.addWidget(self.searchFor)
        self.logsSearcher.returnPressed.connect(self.onSearchBack)
        self.logsSearcher.textChanged.connect(self.onSearchTextChanged)
        self.setCentralWidget(self.logsBrowser)

    def onSearchTextChanged(self):
        pass

    def onSearchBack(self):
        flags = QTextDocument.FindCaseSensitively | QTextDocument.FindBackward
        self.searchText(flags)

    def onSearchForward(self):
        flags = QTextDocument.FindCaseSensitively
        self.searchText(flags)

    def searchText(self, flags):
        text = self.logsSearcher.text()
        if text:
            self.logsBrowser.find(text, flags)

    def hideEvent(self, event):
        self.hidden.emit()
        super().hideEvent(event)


class MainWindowLogHandler(Handler, StringFormatterHandlerMixin):
    """
    Custom logbook handler that logs to the status bar

    Should be moved to a separate module
    """

    modulesColorTable = {
        'galacteek.ui.resource': '#7f8491',
        'galacteek.did.ipid': '#FA8A47',
        'galacteek.core.profile': 'blue'
    }

    def __init__(self, logsBrowser, application_name=None, address=None,
                 facility='user', level=0, format_string=None,
                 filter=None, bubble=True, window=None):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, easyFormatString)
        self.application_name = application_name
        self.window = window
        self.logsBrowser = logsBrowser

    def emit(self, record):
        fRecord = self.format(record)

        if record.level_name == 'INFO':
            color = self.modulesColorTable.get(record.module, 'black')
            self.window.statusMessage(
                "<p style='color: {color}'>{msg}</p>\n".format(
                    color=color, msg=fRecord))

        self.logsBrowser.append(fRecord)

        if not self.logsBrowser.isVisible():
            self.logsBrowser.moveCursor(QTextCursor.End)


class IPFSDaemonStatusWidget(QWidget):
    def __init__(self, bwStatsView, peersStatsView, parent=None):
        super(IPFSDaemonStatusWidget, self).__init__(
            parent, Qt.Popup | Qt.FramelessWindowHint)

        self.app = QApplication.instance()
        self.ui = ui_ipfsinfos.Ui_IPFSInfosDialog()
        self.ui.setupUi(self)
        self.setWindowTitle(iIpfsInfos())

        self.labels = [self.ui.repoObjCount,
                       self.ui.repoVersion,
                       self.ui.repoSize,
                       self.ui.repoMaxStorage,
                       self.ui.nodeId,
                       self.ui.agentVersion,
                       self.ui.protocolVersion]

        self.ui.bwRateStatsLayout.addWidget(bwStatsView)
        self.ui.peersStatsLayout.addWidget(peersStatsView)

        self.setMinimumWidth(self.app.desktopGeometry.width() / 2)
        self.ui.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.ui.tabWidget.setStyleSheet(
            "QTabWidget::pane { background-color: lightgray; }")

    def enableLabels(self, enable):
        for label in self.labels:
            if not enable:
                label.setText('Fetching ...')

            label.setEnabled(enable)

    @ipfsOp
    async def update(self, ipfsop):
        self.enableLabels(False)
        try:
            repoStat = await ipfsop.client.repo.stat()
            idInfo = await ipfsop.client.core.id()
        except BaseException:
            for label in self.labels:
                label.setText(iUnknown())
        else:
            self.ui.repoObjCount.setText(str(repoStat.get(
                'NumObjects', iUnknown())))
            self.ui.repoVersion.setText(str(repoStat.get(
                'Version', iUnknown())))
            self.ui.repoSize.setText(sizeFormat(repoStat.get(
                'RepoSize', 0)))
            self.ui.repoMaxStorage.setText(sizeFormat(repoStat.get(
                'StorageMax', 0)))

            self.ui.nodeId.setText(idInfo.get('ID', iUnknown()))
            self.ui.agentVersion.setText(idInfo.get(
                'AgentVersion', iUnknown()))
            self.ui.protocolVersion.setText(idInfo.get('ProtocolVersion',
                                                       iUnknown()))
            self.enableLabels(True)


class DatabasesManager(QObject):
    def __init__(self, orbitConnector, parent=None):
        super().__init__(parent)

        self.mainW = parent

        self.icon = getIcon('orbitdb.png')
        self.connector = orbitConnector
        self._dbButton = self.buildButton()

    @property
    def button(self):
        return self._dbButton

    def buildButton(self):
        dbButton = QToolButton(self)
        dbButton.setIconSize(QSize(24, 24))
        dbButton.setIcon(self.icon)
        dbButton.setPopupMode(QToolButton.MenuButtonPopup)

        self.databasesMenu = QMenu(self)
        self.mainFeedAction = QAction(self.icon,
                                      'General discussions feed', self,
                                      triggered=self.onMainFeed)
        self.databasesMenu.addAction(self.mainFeedAction)
        dbButton.setMenu(self.databasesMenu)
        return dbButton

    def onMainFeed(self):
        database = self.connector.database('feeds', 'general')
        view = orbital.OrbitFeedView(self.connector, database,
                                     parent=self.mainW.tabWidget)
        self.mainW.registerTab(view, 'General', current=True,
                               icon=self.icon)


class MiscToolBar(QToolBar):
    moved = pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName('miscToolBar')
        self.setAllowedAreas(
            Qt.RightToolBarArea
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def contextMenuEvent(self, event):
        # no context menu
        pass


class MainToolBar(QToolBar):
    moved = pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName('mainToolBar')

        self.setFloatable(False)
        self.setAllowedAreas(
            Qt.LeftToolBarArea | Qt.TopToolBarArea
        )
        self.setContextMenuPolicy(Qt.NoContextMenu)

        # Empty widget
        self.emptySpace = QWidget()
        self.emptySpace.setSizePolicy(
            QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.lastPos = None

    @property
    def vertical(self):
        return self.orientation() == Qt.Vertical

    @property
    def horizontal(self):
        return self.orientation() == Qt.Horizontal

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        pass


class WorkspacesToolBar(QToolBar):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.wsButtons = {}
        self.wsPlanetsToolBar = QToolBar()
        self.wsPlanetsToolBarAdded = False
        self.setAcceptDrops(True)

    def dragEnterEvent(self, ev):
        ev.accept()

    def add(self, btn, dst='default'):
        if dst == 'default':
            self.wsButtons[btn] = self.addWidget(btn)
        elif dst == 'planets':
            if not self.wsPlanetsToolBarAdded:
                # change that soon this is wrong
                self.addWidget(self.wsPlanetsToolBar)
                self.wsPlanetsToolBarAdded = True

            self.wsButtons[btn] = self.wsPlanetsToolBar.addWidget(btn)

    def buttonForWorkspace(self, workspace):
        for wsButton in self.wsButtons.keys():
            if wsButton.workspace is workspace:
                return wsButton

    def wsSwitched(self, workspace):
        # Current workspace has changed, update the buttons

        for wsButton in self.wsButtons.keys():
            if wsButton.workspace is workspace:
                wsButton.setChecked(True)
                wsButton.styleActive()
            else:
                # Repaint when unchecking an inactive workspace, in
                # rare cases it seems to still appear checked
                wsButton.setChecked(False)
                wsButton.repaint()


class WorkspaceSwitchButton(QToolButton, URLDragAndDropProcessor):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.workspace = workspace
        self.setIcon(workspace.wsIcon)
        self.setObjectName('wsSwitchButton')
        self.setProperty("dropping", "false")
        self.setAcceptDrops(True)

        self.setToolTip(workspace.wsToolTip())

        self.ipfsObjectDropped.connect(self.onObjDropped)

    def flashToolTip(self):
        QToolTip.showText(
            self.mapToGlobal(QPoint(0, 0)),
            self.workspace.wsToolTip())

    def dragEnterEvent(self, event):
        if self.workspace.acceptsDrops:
            self.setProperty("dropping", "true")
            self.setStyle(QApplication.style())
            self.flashToolTip()
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dropping", "false")
        self.setStyle(QApplication.style())
        super().dragLeaveEvent(event)

    def onObjDropped(self, path):
        ensure(self.workspace.handleObjectDrop(path))

    def checkStateSet(self):
        super(WorkspaceSwitchButton, self).checkStateSet()

    def nextCheckState(self):
        if self.workspace.stack.currentWorkspace() is not self.workspace:
            self.switch()
            self.setChecked(True)
        else:
            self.setChecked(False)

    def switch(self, soundNotify=False):
        self.workspace.wsSwitch(soundNotify=soundNotify)

    def styleNotify(self):
        self.setStyleSheet('''
            QToolButton {
                background-color: #B7CDC2;
            }
        ''')

    def styleActive(self):
        self.setStyleSheet('''
            QToolButton::hover {
                background-color: #4a9ea1;
            }

            QToolBar QToolButton::pressed {
                background-color: #eec146;
            }
        ''')


class CentralStack(QStackedWidget):
    """
    Stacked widget holding the workspaces
    """

    def __init__(self, parent, wsToolBar):
        super().__init__(parent=parent)

        self.currentChanged.connect(
            partialEnsure(self.onWorkspaceChanged))
        self.toolBarWs = wsToolBar

        self.__wsDormant = []

    @property
    def mainWindow(self):
        return self.parent()

    def workspaces(self):
        for idx in range(0, self.count()):
            yield idx, self.workspaceFromIndex(idx)

        for ws in self.__wsDormant:
            yield -1, ws

    def workspacesBeforeIndex(self, widx):
        for idx in range(widx, self.count()):
            yield idx, self.workspaceFromIndex(idx)

    def workspaceFromIndex(self, idx):
        return self.widget(idx)

    def currentWorkspace(self):
        return self.currentIndex(), self.workspaceFromIndex(
            self.currentIndex())

    def previousWorkspace(self, w):
        idx = self.indexOf(w)

        if idx > 0:
            return idx - 1, self.widget(idx - 1)

        return -1, None

    def nextWorkspace(self, w):
        idx = self.indexOf(w)

        if idx < self.count():
            return idx + 1, self.widget(idx + 1)

        return -1, None

    def activateWorkspaces(self, flag=True):
        for idx, workspace in self.workspaces():
            workspace.setEnabled(flag)

    async def onWorkspaceChanged(self, idx):
        wspace = self.workspaceFromIndex(idx)
        if wspace:
            await wspace.workspaceSwitched()

        self.toolBarWs.wsSwitched(wspace)

    def __addWorkspace(self, workspace):
        if not workspace.wsAttached:
            self.addWidget(workspace)
            workspace.wsAttached = True
            self.toolBarWs.add(
                self.wsSwitchButton(workspace),
                dst=workspace.wsSection
            )
            workspace.setupWorkspace()

    def addWorkspace(self, workspace, section='default', dormant=False):
        workspace.wsSection = section

        if not dormant:
            self.__addWorkspace(workspace)
        else:
            self.__wsDormant.append(workspace)

    def addWorkspaces(self, *wspaces):
        [self.addWorkspace(w) for w in wspaces]

    def workspaceByName(self, name):
        for idx in range(self.count()):
            w = self.widget(idx)
            if w.wsName == name:
                return idx, w

        return None, None

    def workspaceCtx(self, name, show=True):
        idx, wspace = self.workspaceByName(name)
        if wspace:
            if show and self.currentWorkspace() is not wspace:
                wspace.wsSwitch()

            return wspace

    def createSwitchButton(self, wspace, pwspace, nwspace):
        return SwitchButton(pwspace, nwspace, self)

    def wsSwitchButton(self, wspace):
        return WorkspaceSwitchButton(wspace)

    def wsAddGlobalCustomAction(self, *args, **kw):
        for widx, ws in self.workspaces():
            ws.wsAddCustomAction(*args, **kw)

    def wsAddGlobalAction(self, action: QAction):
        for widx, ws in self.workspaces():
            ws.wsAddAction(action)

    def wsActivityNotify(self, workspace):
        widx, curWorkspace = self.currentWorkspace()
        wsButton = self.toolBarWs.buttonForWorkspace(workspace)

        if wsButton and curWorkspace is not workspace:
            wsButton.styleNotify()

    def wsHashmarkTagRulesRun(self, hashmark):
        for idx, workspace in self.workspaces():
            if workspace.wsTagRulesMatchesHashmark(hashmark):
                if idx == -1:
                    self.__addWorkspace(workspace)
                    self.__wsDormant.remove(workspace)

                return workspace

        return None


class BrowseButton(PopupToolButton):
    """
    Browse button. When the button is hovered we play the
    rotating cube clip.
    """

    def __init__(self, parent):
        super().__init__(parent=parent, mode=QToolButton.InstantPopup)

        self.animatedActions = []
        self.rotatingCubeClip = RotatingCubeClipSimple()
        self.rotatingCubeClip.finished.connect(
            functools.partial(self.rotatingCubeClip.start))
        self.rotatingCubeClip.frameChanged.connect(self.onCubeClipFrame)
        self.normalIcon()

    def setMenu(self, menu):
        super(BrowseButton, self).setMenu(menu)

        menu.triggered.connect(lambda action: self.normalIcon())
        menu.aboutToHide.connect(self.normalIcon)

    def onCubeClipFrame(self, no):
        icon = self.rotatingCubeClip.createIcon()

        self.setIcon(icon)

        if self.menu and self.menu.isVisible():
            for action in self.menu.actions():
                if action in self.animatedActions:
                    action.setIcon(icon)

    def rotateCube(self):
        if not self.rotatingCubeClip.playing():
            self.rotatingCubeClip.start()

    def normalIcon(self):
        self.rotatingCubeClip.stop()
        self.setIcon(getIconIpfs64())

    def enterEvent(self, event):
        self.rotateCube()
        super(BrowseButton, self).enterEvent(event)

    def leaveEvent(self, event):
        if not self.menu.isVisible() and self.isEnabled():
            self.normalIcon()

        super(BrowseButton, self).leaveEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, app):
        super(MainWindow, self).__init__()

        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint
        )

        self.showMaximized()
        self._app = app
        self._allTabs = []
        self._lastFeedMark = None

        self.menuBar().hide()

        # Seems reasonable
        self.setMinimumSize(QSize(
            self.app.desktopGeometry.width() / 2,
            self.app.desktopGeometry.height() / 2)
        )

        # User logs widget
        self.logsPopupWindow = UserLogsWindow()
        self.logsPopupWindow.setObjectName('logsTextWindow')
        self.logsPopupWindow.setWindowTitle('{}: logs'.format(GALACTEEK_NAME))
        self.logsPopupWindow.hide()

        self.logsPopupWindow.setMinimumSize(QSize(
            (2 * self.app.desktopGeometry.width()) / 3,
            self.app.desktopGeometry.height() / 2
        ))

        self.userLogsHandler = MainWindowLogHandler(
            self.logsPopupWindow.logsBrowser, window=self,
            level='DEBUG' if self.app.debugEnabled else 'INFO')

        loggerMain.handlers.append(self.userLogsHandler)
        loggerUser.handlers.append(self.userLogsHandler)

        self.menuManual = QMenu(iManual(), self)

        # DID explorer
        self.didExplorer = DIDExplorer()

        # Global pin-all button
        self.pinAllGlobalButton = QToolButton(self)
        self.pinAllGlobalButton.setIcon(getIcon('pin.png'))
        self.pinAllGlobalButton.setObjectName('pinGlobalButton')
        self.pinAllGlobalButton.setToolTip(iGlobalAutoPinning())
        self.pinAllGlobalButton.setCheckable(True)
        self.pinAllGlobalButton.setAutoRaise(True)
        self.pinAllGlobalChecked = False
        self.pinAllGlobalButton.toggled.connect(self.onToggledPinAllGlobal)
        self.pinAllGlobalButton.setChecked(self.app.settingsMgr.browserAutoPin)

        self.toolbarMain = MainToolBar(self)
        self.toolbarPyramids = MultihashPyramidsToolBar(self)
        self.toolbarWs = WorkspacesToolBar()

        self.toolbarMain.orientationChanged.connect(self.onMainToolbarMoved)
        self.toolbarTools = QToolBar()
        self.toolbarTools.setOrientation(self.toolbarMain.orientation())

        # Apps/shortcuts toolbar
        self.qaToolbar = QuickAccessToolBar(self)
        self.qaToolbar.setOrientation(self.toolbarMain.orientation())

        # Main actions and browse button setup
        self.quitAction = QAction(getIcon('quit.png'),
                                  iQuit(),
                                  shortcut=QKeySequence('Ctrl+q'),
                                  triggered=self.quit)
        self.quitAction.setShortcutVisibleInContextMenu(True)

        self.restartAction = QAction(getIcon('quit.png'),
                                     iRestart(),
                                     shortcut=QKeySequence('Alt+Shift+r'),
                                     triggered=self.app.restart)

        self.mPlayerOpenAction = QAction(getIcon('multimedia.png'),
                                         iMediaPlayer(),
                                         triggered=self.onOpenMediaPlayer)

        self.psniffAction = QAction(getIcon('network-transmit.png'),
                                    iPubSubSniff(),
                                    self,
                                    triggered=self.openPsniffTab)

        self.searchServicesAction = QAction(getIcon('ipservice.png'),
                                            'Search IP services',
                                            self,
                                            shortcut=QKeySequence('Ctrl+i'),
                                            triggered=self.onSearchServices)

        self.editorOpenAction = QAction(getIcon('text-editor.png'),
                                        iTextEditor(),
                                        triggered=self.addEditorTab)

        self.editorOpenAction = QAction(getIcon('text-editor.png'),
                                        iTextEditor(),
                                        triggered=self.addEditorTab)

        self.browseAction = QAction(
            getIconIpfsIce(),
            iBrowse(),
            shortcut=QKeySequence('Ctrl+t'),
            triggered=self.onOpenBrowserTabClicked)
        self.browseAction.setShortcutVisibleInContextMenu(True)
        self.browseAutopinAction = QAction(
            getIconIpfsIce(),
            iBrowseAutoPin(),
            shortcut=QKeySequence('Ctrl+Alt+t'),
            triggered=functools.partial(self.onOpenBrowserTabClicked,
                                        pinBrowsed=True))
        self.browseAutopinAction.setShortcutVisibleInContextMenu(True)

        self.seedAppImageAction = QAction(
            getIcon('appimage.png'),
            'Seed AppImage',
            triggered=self.onSeedAppImage
        )

        self.browseButton = BrowseButton(self)
        self.browseButton.setPopupMode(QToolButton.InstantPopup)
        self.browseButton.setObjectName('buttonBrowseIpfs')
        self.browseButton.normalIcon()

        self.browseButton.menu.addAction(self.browseAction)
        self.browseButton.menu.addAction(self.browseAutopinAction)
        self.browseButton.menu.addSeparator()
        self.browseButton.menu.addAction(self.searchServicesAction)
        self.browseButton.menu.addSeparator()
        self.browseButton.menu.addAction(self.editorOpenAction)
        self.browseButton.menu.addSeparator()

        if not self.app.cmdArgs.seed and self.app.cmdArgs.appimage:
            # Add the possibility to import the image from the menu
            # if not specified on the command-line
            self.browseButton.menu.addAction(self.seedAppImageAction)
            self.browseButton.menu.addSeparator()

        self.browseButton.menu.addAction(self.quitAction)

        self.browseButton.animatedActions = [
            self.browseAction,
            self.browseAutopinAction
        ]
        self.browseButton.rotateCube()

        # File manager
        self.fileManagerWidget = files.FileManager(parent=self)

        if 0:
            # Text editor button
            self.textEditorButton = QToolButton(self)
            self.textEditorButton.setToolTip(iTextEditor())
            self.textEditorButton.setIcon(getIcon('text-editor.png'))
            self.textEditorButton.clicked.connect(self.addEditorTab)

        # Camera controller
        self.cameraController = CameraController(parent=self)

        # Edit-Profile button
        self.menuUserProfile = QMenu(self)
        self.profilesActionGroup = QActionGroup(self)

        # Profile button
        self.profileMenu = QMenu(self)
        iconProfile = getIcon('helmet.png')
        self.profileMenu.addAction(iconProfile,
                                   'Edit profile',
                                   self.onProfileEditDialog)
        self.profileMenu.addSeparator()

        self.userWebsiteManager = userwebsite.UserWebsiteManager(
            parent=self.profileMenu)

        self.profileButton = ProfileButton(
            menu=self.profileMenu,
            icon=iconProfile
        )
        self.profileButton.setEnabled(False)

        # Hashmarks searcher
        self.hashmarksSearcher = HashmarksSearcher(parent=self)
        self.hashmarksSearcher.setToolTip(iHashmarksLibrary())
        self.hashmarksSearcher.setShortcut(QKeySequence('Ctrl+Alt+h'))

        self.hashmarkMgrButton = HashmarkMgrButton(
            marks=self.app.marksLocal)
        self.hashmarkMgrButton.menu.addMenu(self.hashmarksSearcher.menu)

        self.hashmarkMgrButton.menu.addSeparator()

        self.clipboardItemsStack = ClipboardItemsStack(parent=self.toolbarMain)

        # Clipboard loader button
        self.clipboardManager = ClipboardManager(
            self.app.clipTracker,
            self.clipboardItemsStack,
            self.app.resourceOpener,
            icon=getIcon('clipboard.png'),
            parent=self.toolbarMain
        )

        # Atom
        self.atomButton = AtomFeedsToolbarButton()

        # Settings button
        settingsIcon = getIcon('settings.png')
        self.settingsToolButton = QToolButton(self)
        self.settingsToolButton.setIcon(settingsIcon)
        self.settingsToolButton.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        menu.addAction(settingsIcon, iSettings(),
                       self.onSettings)
        menu.addSeparator()
        menu.addAction(settingsIcon, iEventLog(),
                       self.onOpenEventLog)
        menu.addAction(getIcon('lock-and-key.png'), iKeys(),
                       self.onIpfsKeysClicked)
        menu.addSeparator()

        if self.app.debugEnabled:
            menu.addAction(self.psniffAction)
            menu.addSeparator()

        menu.addAction(iClearHistory(), self.onClearHistory)

        self.settingsToolButton.setMenu(menu)

        # Help button
        self.helpToolButton = QToolButton(self)
        self.helpToolButton.setObjectName('helpToolButton')
        self.helpToolButton.setIcon(getIcon('information.png'))
        self.helpToolButton.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        menu.addMenu(self.menuManual)
        menu.addSeparator()

        dMenu = QMenu('Donate', self)
        dMenu.addAction('With Liberapay', self.onHelpDonateLiberaPay)
        dMenu.addAction('With Github Sponsors', self.onHelpDonateGSponsors)
        dMenu.addAction('With Patreon', self.onHelpDonatePatreon)
        menu.addMenu(dMenu)

        menu.addAction('About', self.onAboutGalacteek)
        self.helpToolButton.setMenu(menu)

        # Quit button
        self.quitButton = PopupToolButton(
            parent=self, mode=QToolButton.InstantPopup)
        self.quitButton.setObjectName('quitToolButton')
        self.quitButton.setIcon(self.quitAction.icon())
        self.quitButton.menu.addAction(self.restartAction)
        self.quitButton.menu.addSeparator()
        self.quitButton.menu.addAction(self.quitAction)
        self.quitButton.setToolTip(iQuit())

        self.ipfsSearchPageFactory = ipfssearch.SearchResultsPageFactory(self)

        self.ipfsSearchButton = ipfssearch.IPFSSearchButton(self)
        self.ipfsSearchButton.setShortcut(QKeySequence('Ctrl+Alt+s'))
        self.ipfsSearchButton.setIcon(self.ipfsSearchButton.iconNormal)
        self.ipfsSearchButton.setToolTip(iSearchIpfsContent())
        self.ipfsSearchButton.clicked.connect(self.addIpfsSearchView)

        self.toolbarMain.addWidget(self.browseButton)
        self.toolbarMain.addWidget(self.hashmarkMgrButton)
        self.toolbarMain.addWidget(self.hashmarksSearcher)
        self.toolbarMain.addWidget(self.profileButton)

        self.toolbarMain.addSeparator()
        self.toolbarMain.addWidget(self.toolbarWs)
        self.toolbarMain.addSeparator()
        self.toolbarMain.addWidget(self.cameraController)
        self.toolbarMain.addSeparator()

        self.hashmarkMgrButton.hashmarkClicked.connect(self.onHashmarkClicked)
        self.hashmarksSearcher.hashmarkClicked.connect(self.onHashmarkClicked)

        self.toolbarMain.addWidget(self.qaToolbar)

        self.toolbarMain.actionStatuses = self.toolbarMain.addAction(
            'Statuses')
        self.toolbarMain.actionStatuses.setVisible(False)

        self.toolbarMain.addWidget(self.toolbarMain.emptySpace)
        self.toolbarMain.addSeparator()
        self.toolbarMain.addWidget(self.clipboardItemsStack)
        self.toolbarMain.addWidget(self.clipboardManager)
        self.toolbarMain.addSeparator()

        self.toolbarMain.addWidget(self.pinAllGlobalButton)
        self.toolbarMain.addWidget(self.settingsToolButton)

        self.toolbarMain.addWidget(self.helpToolButton)
        self.toolbarMain.addSeparator()
        self.toolbarMain.addWidget(self.quitButton)

        self.addToolBar(Qt.TopToolBarArea, self.toolbarMain)
        self.addToolBar(Qt.RightToolBarArea, self.toolbarPyramids)

        self.stack = CentralStack(self, self.toolbarWs)

        self.wspacePeers = WorkspacePeers(self.stack)
        self.wspaceFs = WorkspaceFiles(self.stack)
        self.wspaceSearch = WorkspaceSearch(self.stack)
        self.wspaceMultimedia = WorkspaceMultimedia(self.stack)
        self.wspaceEdit = WorkspaceEdition(self.stack)
        self.wspaceMisc = WorkspaceMisc(self.stack)

        self.wspaceEarth = PlanetWorkspace(self.stack, 'Earth')
        self.wspaceMars = PlanetWorkspace(self.stack, 'Mars')
        self.wspaceJupiter = PlanetWorkspace(self.stack, 'Jupiter')
        self.wspaceMercury = PlanetWorkspace(self.stack, 'Mercury')
        self.wspaceNeptune = PlanetWorkspace(self.stack, 'Neptune')
        self.wspacePluto = PlanetWorkspace(self.stack, 'Pluto')

        self.webProfile = QtWebEngineWidgets.QWebEngineProfile.defaultProfile()

        # Status bar setup
        self.pinningStatusButton = QPushButton(self)
        self.pinningStatusButton.setShortcut(
            QKeySequence('Ctrl+u'))
        self.pinningStatusButton.setToolTip(iNoStatus())
        self.pinningStatusButton.setIcon(getIcon('pin-black.png'))
        self.pinningStatusButton.clicked.connect(
            self.showPinningStatusWidget)
        self.pubsubStatusButton = QPushButton(self)
        self.pubsubStatusButton.setIcon(getIcon('network-offline.png'))

        self.ipfsStatusCube = AnimatedLabel(
            RotatingCubeRedFlash140d(speed=10),
            parent=self
        )
        self.ipfsStatusCube.clip.setScaledSize(QSize(24, 24))
        self.ipfsStatusCube.hovered.connect(self.onIpfsInfosHovered)
        self.ipfsStatusCube.startClip()

        self.statusbar = self.statusBar()
        self.userLogsButton = QToolButton(self)
        self.userLogsButton.setToolTip('Logs')
        self.userLogsButton.setIcon(getIcon('information.png'))
        self.userLogsButton.setCheckable(True)
        self.userLogsButton.toggled.connect(self.onShowUserLogs)
        self.logsPopupWindow.hidden.connect(
            functools.partial(self.userLogsButton.setChecked, False))

        # Bandwidth graph
        self.bwGraphView = BandwidthGraphView(parent=None)
        self.peersGraphView = PeersCountGraphView(parent=None)
        self.ipfsDaemonStatusWidget = IPFSDaemonStatusWidget(
            self.bwGraphView, self.peersGraphView)

        self.lastLogLabel = QLabel(self.statusbar)
        self.lastLogLabel.setAlignment(Qt.AlignLeft)
        self.lastLogLabel.setObjectName('lastLogLabel')
        self.statusbar.insertWidget(0, self.lastLogLabel, 1)

        self.statusbar.addPermanentWidget(self.ipfsStatusCube)

        self.ethereumStatusBtn = EthereumStatusButton(parent=self)
        self.statusbar.addPermanentWidget(self.ethereumStatusBtn)

        self.statusbar.addPermanentWidget(self.pinningStatusButton)
        self.statusbar.addPermanentWidget(self.pubsubStatusButton)
        self.statusbar.addPermanentWidget(self.userLogsButton)

        # Connection status timer
        self.timerStatus = QTimer(self)
        self.timerStatus.timeout.connect(self.onMainTimerStatus)
        self.timerStatus.start(7000)

        self.enableButtons(False)

        # Docks
        self.pSearchDock = PeersServiceSearchDock(self.app.peersTracker, self)
        self.pSearchDock.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.pSearchDock)

        # Connect the IPFS context signals
        self.app.ipfsCtx.ipfsConnectionReady.connectTo(self.onConnReady)
        self.app.ipfsCtx.ipfsRepositoryReady.connectTo(self.onRepoReady)

        self.app.ipfsCtx.pubsub.psMessageRx.connect(self.onPubsubRx)
        self.app.ipfsCtx.pubsub.psMessageTx.connect(self.onPubsubTx)
        self.app.ipfsCtx.profilesAvailable.connect(self.onProfilesList)
        self.app.ipfsCtx.profileChanged.connect(self.onProfileChanged)
        self.app.ipfsCtx.pinItemStatusChanged.connect(self.onPinStatusChanged)
        self.app.ipfsCtx.pinItemsCount.connect(self.onPinItemsCount)
        self.app.ipfsCtx.pinFinished.connect(self.onPinFinished)

        # Misc signals
        database.IPNSFeedMarkAdded.connectTo(self.onFeedMarkAdded)
        self.app.systemTray.messageClicked.connect(self.onSystrayMsgClicked)

        # Application signals
        self.app.manualAvailable.connect(self.onManualAvailable)

        previousGeo = self.app.settingsMgr.mainWindowGeometry
        if previousGeo:
            self.restoreGeometry(previousGeo)
        previousState = self.app.settingsMgr.mainWindowState
        if previousState:
            self.restoreState(previousState)

        self.hashmarksPage = None

        self.pinIconLoading = getIcon('pin-blue-loading.png')
        self.pinIconNormal = getIcon('pin-black.png')

        self.setCentralWidget(self.stack)

    @property
    def tabWidget(self):
        cur = self.stack.currentWidget()
        if cur:
            return cur.tabWidget

    @property
    def app(self):
        return self._app

    @property
    def allTabs(self):
        return self._allTabs

    def keyPressEvent(self, event):
        modifiers = event.modifiers()

        widx, curWorkspace = self.stack.currentWorkspace()

        if modifiers & Qt.ControlModifier:
            if event.key() == Qt.Key_W and curWorkspace:
                idx = curWorkspace.tabWidget.currentIndex()
                ensure(curWorkspace.onTabCloseRequest(idx))

        super(MainWindow, self).keyPressEvent(event)

    def setupWorkspaces(self):
        self.stack.addWorkspace(self.wspaceFs)
        self.stack.addWorkspace(
            self.wspaceEarth, section='planets')
        self.stack.addWorkspace(
            self.wspaceMars, section='planets', dormant=True)
        self.stack.addWorkspace(
            self.wspaceJupiter, section='planets', dormant=True)
        self.stack.addWorkspace(
            self.wspaceMercury, section='planets', dormant=True)
        self.stack.addWorkspace(
            self.wspaceNeptune, section='planets', dormant=True)
        self.stack.addWorkspace(
            self.wspacePluto, section='planets', dormant=True)

        self.stack.addWorkspace(self.wspacePeers)
        self.stack.addWorkspace(self.wspaceSearch)
        self.stack.addWorkspace(self.wspaceEdit)
        self.stack.addWorkspace(self.wspaceMultimedia)
        self.stack.addWorkspace(self.wspaceMisc)

        self.stack.wsAddGlobalAction(self.browseAction)
        self.stack.activateWorkspaces(False)

    def onSeedAppImage(self):
        ensure(self.app.seedAppImage())

    def onClearHistory(self):
        self.app.urlHistory.clear()

    def onHashmarkClicked(self, hashmark):
        ensure(self.app.resourceOpener.openHashmark(hashmark))

    def onMainToolbarMoved(self, orientation):
        self.toolbarMain.lastPos = self.toolbarMain.pos()

        self.toolbarTools.setOrientation(orientation)
        self.qaToolbar.setOrientation(orientation)
        self.toolbarWs.setOrientation(orientation)

        if self.toolbarMain.vertical:
            self.toolbarMain.emptySpace.setSizePolicy(
                QSizePolicy.Minimum, QSizePolicy.Expanding)
            self.qaToolbar.setMinimumHeight(
                self.toolbarMain.height() / 3)
            self.qaToolbar.setMinimumWidth(32)
        elif self.toolbarMain.horizontal:
            self.qaToolbar.setMinimumWidth(
                self.width() / 3)
            self.qaToolbar.setMinimumHeight(32)
            self.toolbarMain.emptySpace.setSizePolicy(QSizePolicy.Expanding,
                                                      QSizePolicy.Minimum)

    def onOpenEventLog(self):
        self.addEventLogTab(current=True)

    def onShowUserLogs(self, checked):
        lowerPos = self.mapToGlobal(QPoint(self.width(), self.height()))

        popupPoint = QPoint(
            lowerPos.x() - self.logsPopupWindow.width() - 64,
            lowerPos.y() - self.logsPopupWindow.height() - 64
        )

        self.logsPopupWindow.move(popupPoint)
        self.logsPopupWindow.logsBrowser.moveCursor(QTextCursor.End)
        self.logsPopupWindow.setVisible(checked)

    def onProfileEditDialog(self):
        runDialog(ProfileEditDialog, self.app.ipfsCtx.currentProfile,
                  title='IP profile')

    def onProfileWebsiteUpdated(self):
        self.profileButton.setStyleSheet('''
            QToolButton {
                background-color: #B7CDC2;
            }
        ''')
        self.app.loop.call_later(
            3, self.profileButton.setStyleSheet,
            'QToolButton {}'
        )

    @asyncify
    async def onProfileChanged(self, pName, profile):
        self.profileButton.setEnabled(False)

        if not profile.initialized:
            return

        def hashmarksLoaded(nodeId, hmarks):
            try:
                self.hashmarksSearcher.register(nodeId, hmarks)
            except Exception as err:
                log.debug(str(err))

        profile.sharedHManager.hashmarksLoaded.connect(hashmarksLoaded)

        await profile.userInfo.loaded
        self.profileButton.setEnabled(True)

        await self.profileButton.changeProfile(profile)

        for action in self.profilesActionGroup.actions():
            if action.data() == pName:
                action.setChecked(True)

                # Refresh the file manager
                fmTab = self.findTabFileManager()

                if fmTab:
                    fmTab.fileManager.setupModel()
                    fmTab.fileManager.pathSelectorDefault()

    def onProfilesList(self, pList):
        currentList = [action.data() for action in
                       self.profilesActionGroup.actions()]

        for pName in pList:
            if pName in currentList:
                continue

            action = QAction(self.profilesActionGroup,
                             checkable=True, text=pName)
            action.setData(pName)

        for action in self.profilesActionGroup.actions():
            self.menuUserProfile.addAction(action)

    async def onRepoReady(self):
        self.browseButton.normalIcon()
        self.stack.activateWorkspaces(True)

        self.fileManagerWidget.setupModel()

        await self.app.ipfsCtx.peers.watchNetworkGraph()

        await self.displayConnectionInfo()
        await self.app.marksLocal.pyramidsInit()
        await self.app.sqliteDb.feeds.start()
        await self.hashmarkMgrButton.updateMenu()
        await self.hashmarkMgrButton.updateIcons()
        await self.qaToolbar.init()

        with self.stack.workspaceCtx(WS_FILES, show=False) as ws:
            await ws.seedsSetup()

        with self.stack.workspaceCtx(WS_PEERS, show=False) as ws:
            await ws.chatJoinDefault()

        with self.stack.workspaceCtx('@Earth', show=False) as ws:
            await ws.loadDapps()

        self.enableButtons()

    @ipfsOp
    async def orbitStart(self, ipfsop):
        resp = await self.app.ipfsCtx.orbitConnector.start()

        if resp:
            orbitIcon = QPushButton()
            orbitIcon.setIcon(getIcon('orbitdb.png'))
            orbitIcon.setToolTip('OrbitDB: connected')
            self.statusbar.addPermanentWidget(orbitIcon)

            self.orbitManager = DatabasesManager(
                self.app.ipfsCtx.orbitConnector, self)
            self.toolbarTools.addWidget(self.orbitManager.button)

            await ipfsop.ctx.currentProfile.orbitalSetup(
                self.app.ipfsCtx.orbitConnector)

    def onSystrayMsgClicked(self):
        # Open last shown mark in the systray
        if self._lastFeedMark is not None:
            self.addBrowserTab().browseFsPath(self._lastFeedMark.path)

    async def onFeedMarkAdded(self, feed, mark):
        self._lastFeedMark = mark

        message = """New entry in IPNS feed {feed}: {title}.
                 Click the message to open it""".format(
            feed=feed.name,
            title=mark.title if mark.title else 'No title'
        )

        self.app.systemTrayMessage('IPNS', message, timeout=10000)

    def onIpfsInfosHovered(self, hovered):
        if hovered is False:
            return

        statusCubePos = self.ipfsStatusCube.mapToGlobal(QPoint(0, 0))

        popupPoint = QPoint(
            statusCubePos.x() - self.ipfsDaemonStatusWidget.width() -
            self.ipfsStatusCube.width(),
            statusCubePos.y() - self.ipfsDaemonStatusWidget.height() -
            self.ipfsStatusCube.height()
        )

        self.ipfsDaemonStatusWidget.move(popupPoint)
        self.ipfsDaemonStatusWidget.setVisible(hovered)
        ensure(self.ipfsDaemonStatusWidget.update())

    async def onConnReady(self):
        pass

    def onPubsubRx(self):
        now = QDateTime.currentDateTime()
        self.pubsubStatusButton.setIcon(getIcon('network-transmit.png'))
        self.pubsubStatusButton.setToolTip(
            'Pubsub: last message received {}'.format(now.toString()))

    def onPubsubTx(self):
        pass

    def showPinningStatusWidget(self):
        with self.stack.workspaceCtx(WS_MISC) as ws:
            return ws.tabWidget.setCurrentWidget(
                ws.pinStatusTab)

    def onPinItemsCount(self, count):
        statusMsg = iItemsInPinningQueue(count)

        if count > 0:
            self.pinningStatusButton.setIcon(self.pinIconLoading)
        else:
            self.pinningStatusButton.setIcon(self.pinIconNormal)

        self.pinningStatusButton.setToolTip(statusMsg)
        self.pinningStatusButton.setStatusTip(statusMsg)

    def onPinFinished(self, path):
        pass

    def onPinStatusChanged(self, qname, path, status):
        pass

    def onManualAvailable(self, langCode, entry):
        lang = iLangEnglish() if langCode == 'en' else iUnknown()
        self.menuManual.addAction(lang, functools.partial(
                                  self.onOpenManual, langCode))

    def onOpenManual(self, lang):
        entry = self.app.manuals.getManualEntry(lang)
        if entry:
            self.addBrowserTab(workspace=WS_MISC).browseIpfsHash(entry['Hash'])

    def enableButtons(self, flag=True):
        for btn in [
                self.clipboardManager,
                self.browseButton,
                self.cameraController,
                self.hashmarkMgrButton,
                self.hashmarksSearcher,
                self.toolbarWs,
                self.profileButton]:
            btn.setEnabled(flag)

    def statusMessage(self, msg):
        self.lastLogLabel.setText(msg)
        self.lastLogLabel.setToolTip(msg)

    def registerTab(self, tab, name, icon=None, current=True,
                    tooltip=None, workspace=None):
        if workspace is None:
            sidx, wspace = self.stack.currentWorkspace()
        elif isinstance(workspace, str):
            sidx, wspace = self.stack.workspaceByName(workspace)
            if wspace is None:
                # XXX
                return
        elif issubclass(workspace.__class__, BaseWorkspace):
            wspace = workspace
        else:
            sidx, wspace = self.stack.currentWorkspace()

        wspace.wsRegisterTab(tab, name, icon=icon, current=current,
                             tooltip=tooltip)

        if self.stack.currentWorkspace() is not wspace:
            wspace.wsSwitch()

    def findTabFileManager(self):
        with self.stack.workspaceCtx(WS_FILES) as ws:
            return ws.wsFindTabWithId('filemanager')

    def findTabIndex(self, w):
        return self.tabWidget.indexOf(w)

    def findTabWithName(self, name):
        for widx, workspace in self.stack.workspaces():
            tab = workspace.wsFindTabWithName(name)
            if tab:
                return workspace, tab

        return None, None

    def onSettings(self):
        runDialog(settings.SettingsDialog, self.app)

    def onToggledPinAllGlobal(self, checked):
        self.pinAllGlobalChecked = checked

    def onAboutGalacteek(self):
        runDialog(AboutDialog, iAbout())

    def setConnectionInfoMessage(self, msg):
        self.app.systemTray.setToolTip('{app}: {msg}'.format(
            app=GALACTEEK_NAME, msg=msg))
        self.ipfsStatusCube.setToolTip(msg)

    @ipfsOp
    async def displayConnectionInfo(self, ipfsop):
        try:
            info = await ipfsop.client.core.id()
            bwStats = await ipfsop.client.stats.bw()
        except Exception:
            self.setConnectionInfoMessage(iErrNoCx())
            return

        nodeId = info.get('ID', iUnknown())
        nodeAgent = info.get('AgentVersion', iUnknownAgent())

        # Get IPFS peers list
        peers = await ipfsop.peersList()
        peersCount = len(peers)

        if peersCount == 0:
            await ipfsop.noPeersFound()
            self.setConnectionInfoMessage(iCxButNoPeers(nodeId, nodeAgent))
            self.ipfsStatusCube.clip.setSpeed(0)
            return

        await ipfsop.peersCountStatus(peersCount)

        # Notify the bandwidth graph with the stats
        if isinstance(bwStats, dict):
            await self.bwGraphView.bwStatsFetched.emit(bwStats)

        await self.peersGraphView.peersCountFetched.emit(peersCount)

        # TODO: compute something more precise, probably based on the
        # swarm's high/low config
        connQuality = int((peersCount * 100) / 1000)

        self.setConnectionInfoMessage(
            iConnectStatus(nodeId, nodeAgent, peersCount))
        self.ipfsStatusCube.clip.setSpeed(5 + min(connQuality, 80))

    def stopTimers(self):
        self.timerStatus.stop()

    def onMainTimerStatus(self):
        ensure(self.displayConnectionInfo())

    def explore(self, cid):
        ipfsPath = IPFSPath(cid, autoCidConv=True)
        if ipfsPath.valid:
            ensure(self.exploreIpfsPath(ipfsPath))
        else:
            messageBox(iInvalidInput())

    @ipfsOp
    async def exploreIpfsPath(self, ipfsop, ipfsPath):
        cid = await ipfsPath.resolve(ipfsop)
        if not cid:
            return messageBox(iCannotResolve(str(ipfsPath)))

        path = IPFSPath(cid, autoCidConv=True)
        tabName = path.shortRepr()

        tooltip = 'CID explorer: {0}'.format(cid)
        view = unixfs.IPFSHashExplorerStack(self, cid)
        self.registerTab(view, tabName, current=True,
                         icon=getIcon('hash.png'), tooltip=tooltip,
                         workspace=WS_FILES)

    def getMediaPlayer(self):
        with self.stack.workspaceCtx(WS_MULTIMEDIA) as ws:
            return ws.mPlayerTab()

    def mediaPlayerQueue(self, path, playLast=False, mediaName=None):
        tab = self.getMediaPlayer()
        if tab:
            tab.queueFromPath(path, mediaName=mediaName, playLast=playLast)

    def mediaPlayerPlay(self, path, mediaName=None):
        tab = self.getMediaPlayer()
        if tab:
            tab.playFromPath(path, mediaName=mediaName)

    def onTabChanged(self, idx):
        tab = self.tabWidget.widget(idx)
        if tab:
            ensure(tab.onTabChanged())

    def openPsniffTab(self):
        self.registerTab(
            PubsubSnifferWidget(self), iPubSubSniff(), current=True,
            workspace=WS_MISC)

    def addEditorTab(self, path=None, editing=True):
        tab = TextEditorTab(editing=editing, parent=self)

        if isinstance(path, IPFSPath) and path.valid:
            tab.editor.display(path)

        self.registerTab(tab, iTextEditor(),
                         icon=getIcon('text-editor.png'), current=True,
                         tooltip=str(path),
                         workspace=WS_EDIT)

    def addIpfsSearchView(self):
        tab = ipfssearch.IPFSSearchTab(self)
        self.registerTab(tab, iIpfsSearch(), current=True,
                         icon=getIcon('search-engine.png'))
        tab.view.browser.setFocus(Qt.OtherFocusReason)

    def onOpenMediaPlayer(self):
        self.getMediaPlayer()

    def onOpenBrowserTabClicked(self, pinBrowsed=False):
        self.addBrowserTab(pinBrowsed=pinBrowsed)

    def onWriteNewDocumentClicked(self):
        w = textedit.AddDocumentWidget(self, parent=self.tabWidget)
        self.registerTab(w, 'New document', current=True)

    def onIpfsKeysClicked(self):
        with self.stack.workspaceCtx(WS_MISC) as ws:
            tab = ws.wsFindTabWithId('ipfs-keys-manager')
            if tab:
                return ws.tabWidget.setCurrentWidget(tab)
            else:
                ws.wsRegisterTab(keys.KeysTab(self), iKeys(), current=True)

    def onHelpDonateGSponsors(self):
        tab = self.app.mainWindow.addBrowserTab(workspace='@Earth')
        tab.enterUrl(QUrl('https://github.com/sponsors/pinnaculum'))

    def onHelpDonateLiberaPay(self):
        tab = self.app.mainWindow.addBrowserTab(workspace='@Earth')
        tab.enterUrl(QUrl('https://liberapay.com/galacteek'))

    def onHelpDonatePatreon(self):
        tab = self.app.mainWindow.addBrowserTab(workspace='@Earth')
        tab.enterUrl(QUrl('https://patreon.com/galacteek'))

    def addBrowserTab(self, label='No page loaded', pinBrowsed=False,
                      minProfile=None, current=True,
                      workspace=None):
        icon = getIconIpfsIce()
        tab = browser.BrowserTab(self,
                                 minProfile=minProfile,
                                 pinBrowsed=pinBrowsed)
        self.registerTab(tab, label, icon=icon, current=current,
                         workspace=workspace)

        if self.app.settingsMgr.isTrue(CFG_SECTION_BROWSER, CFG_KEY_GOTOHOME):
            tab.loadHomePage()
        else:
            tab.focusUrlZone()

        return tab

    def addEventLogTab(self, current=False):
        self.registerTab(eventlog.EventLogWidget(self), iEventLog(),
                         current=current,
                         workspace=WS_MISC)

    def quit(self):
        # Qt and application exit
        self.saveUiSettings()
        self.app.onExit()

    def saveUiSettings(self):
        self.app.settingsMgr.setSetting(
            CFG_SECTION_UI,
            CFG_KEY_MAINWINDOW_GEOMETRY,
            self.saveGeometry())
        self.app.settingsMgr.setSetting(
            CFG_SECTION_UI,
            CFG_KEY_MAINWINDOW_STATE,
            self.saveState())

        self.app.settingsMgr.setSetting(
            CFG_SECTION_UI,
            CFG_KEY_BROWSER_AUTOPIN,
            self.pinAllGlobalButton.isChecked())

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def onIpfsObjectServed(self, ipfsPath, cType, reqTime):
        # TODO
        # Called when an object was served by the native IPFS scheme handler
        pass

    def onSearchServices(self):
        self.pSearchDock.searchMode()

    def getPyrDropButtonFor(self, ipfsPath, origin=None):
        return self.toolbarPyramids.getPyrDropButtonFor(
            ipfsPath, origin=origin)
