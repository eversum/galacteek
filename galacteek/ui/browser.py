import functools
import os.path
import re

from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QActionGroup
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QTextBrowser
from PyQt5.QtWidgets import QLineEdit

from PyQt5.QtPrintSupport import *

from PyQt5.QtCore import QUrl
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtCore import QTimer

from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QImage

from PyQt5 import QtWebEngineWidgets

from PyQt5.QtWebEngineWidgets import QWebEnginePage
from PyQt5.QtWebEngineWidgets import QWebEngineDownloadItem
from PyQt5.QtWebEngineWidgets import QWebEngineSettings
from PyQt5.QtWebEngineWidgets import QWebEngineContextMenuData
from PyQt5.QtWebChannel import QWebChannel

from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor

from PyQt5.QtGui import QKeySequence

from galacteek import log, ensure
from galacteek.ipfs.wrappers import *
from galacteek.ipfs import cidhelpers
from galacteek.ipfs import megabytes
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs.cidhelpers import cidValid
from galacteek.core.analyzer import ResourceAnalyzer

from galacteek.core.schemes import isSchemeRegistered
from galacteek.core.schemes import SCHEME_ENS
from galacteek.core.schemes import SCHEME_IPFS
from galacteek.core.schemes import SCHEME_IPNS
from galacteek.core.schemes import SCHEME_Z
from galacteek.core.schemes import DAGProxySchemeHandler
from galacteek.core.schemes import MultiDAGProxySchemeHandler

from galacteek.core.webprofiles import WP_NAME_IPFS
from galacteek.core.webprofiles import WP_NAME_MINIMAL
from galacteek.core.webprofiles import WP_NAME_WEB3

from galacteek.dweb.webscripts import scriptFromString
from galacteek.dweb.page import BaseHandler
from galacteek.dweb.page import pyqtSlot
from galacteek.dweb.render import renderTemplate
from galacteek.dweb.htmlparsers import IPFSLinksParser

from . import ui_browsertab
from .pin import PinBatchWidget, PinBatchTab
from .helpers import *
from .dialogs import *
from .hashmarks import *
from .i18n import *
from .clipboard import iCopyPathToClipboard
from .clipboard import iClipboardEmpty
from .history import HistoryMatchesWidget
from .widgets import *
from ..appsettings import *

# i18n


def iOpenInTab():
    return QCoreApplication.translate('BrowserTabForm', 'Open link in new tab')


def iOpenHttpInTab():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Open http/https link in new tab')


def iOpenLinkInTab():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Open link in new tab')


def iOpenWith():
    return QCoreApplication.translate('BrowserTabForm', 'Open with')


def iDownload():
    return QCoreApplication.translate('BrowserTabForm', 'Download')


def iSaveWebPage():
    return QCoreApplication.translate(
        'BrowserTabForm', 'Save page to the "Web Pages" folder')


def iJsConsole():
    return QCoreApplication.translate('BrowserTabForm', 'Javascript console')


def iPin():
    return QCoreApplication.translate('BrowserTabForm', 'PIN')


def iPinThisPage():
    return QCoreApplication.translate('BrowserTabForm', 'PIN (this page)')


def iPinRecursive():
    return QCoreApplication.translate('BrowserTabForm', 'PIN (recursive)')


def iFollow():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Follow IPNS resource')


def iEnterIpfsCID():
    return QCoreApplication.translate('BrowserTabForm', 'Enter an IPFS CID')


def iBrowseHomePage():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Go to home page')


def iBrowseIpfsCID():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Browse IPFS resource (CID)')


def iBrowseIpfsMultipleCID():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Browse multiple IPFS resources (CID)')


def iEnterIpfsCIDDialog():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Load IPFS CID dialog')


def iFollowIpnsDialog():
    return QCoreApplication.translate('BrowserTabForm',
                                      'IPNS add feed dialog')


def iBrowseIpnsHash():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Browse IPNS resource from hash/name')


def iBrowseCurrentClipItem():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Browse current clipboard item')


def iEnterIpns():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Enter an IPNS hash/name')


def iEnterIpnsDialog():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Load IPNS key dialog')


def iCreateQaMapping():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Create quick-access mapping')


def iHashmarked(path):
    return QCoreApplication.translate('BrowserTabForm',
                                      'Hashmarked {0}').format(path)


def iHashmarkTitleDialog():
    return QCoreApplication.translate('BrowserTabForm',
                                      'Hashmark title')


def iInvalidUrl(text):
    return QCoreApplication.translate('BrowserTabForm',
                                      'Invalid URL: {0}').format(text)


def iInvalidObjectPath(text):
    return QCoreApplication.translate(
        'BrowserTabForm',
        'Invalid IPFS object path: {0}').format(text)


def iInvalidCID(text):
    return QCoreApplication.translate(
        'BrowserTabForm',
        '{0} is an invalid IPFS CID (Content IDentifier)').format(text)


def iNotAnIpfsResource():
    return QCoreApplication.translate(
        'BrowserTabForm',
        'Not an IPFS resource')


def iWebProfileMinimal():
    return QCoreApplication.translate(
        'BrowserTabForm',
        'Minimal profile')


def iWebProfileIpfs():
    return QCoreApplication.translate(
        'BrowserTabForm',
        'IPFS profile')


def iWebProfileWeb3():
    return QCoreApplication.translate(
        'BrowserTabForm',
        'Web3 profile')


class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        pass


class CurrentPageHandler(BaseHandler):
    def __init__(self, parent):
        super().__init__(parent)

        self.rootCid = None

    @pyqtSlot()
    def getRootCid(self):
        return self.rootCid


class CustomWebPage (QtWebEngineWidgets.QWebEnginePage):
    jsConsoleMessage = pyqtSignal(int, str, int, str)

    def __init__(self, webProfile, parent):
        super(CustomWebPage, self).__init__(webProfile, parent)

    def registerPageHandler(self):
        self.channel = QWebChannel()
        self.setWebChannel(self.channel)
        self.pageHandler = CurrentPageHandler(self)
        self.channel.registerObject('gpage', self.pageHandler)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        self.jsConsoleMessage.emit(level, message, lineNumber, sourceId)

    def registerProtocolHandlerRequestedDisabled(self, request):
        """
        registerProtocolHandlerRequested(request) can be used to
        handle JS 'navigator.registerProtocolHandler()' calls. If
        we want to enable that in the future it'll be done here.
        """

        scheme = request.scheme()
        origin = request.origin()

        qRet = questionBox(
            'registerProtocolHandler',
            'Allow {origin} to register procotol handler for: {h} ?'.format(
                origin=origin.toString(),
                h=scheme
            )
        )

        if qRet is True:
            request.accept()
        else:
            request.reject()

    async def render(self, tmpl, url=None, **ctx):
        if url:
            self.setHtml(await renderTemplate(tmpl, **ctx), url)
        else:
            self.setHtml(await renderTemplate(tmpl, **ctx))


class JSConsoleWidget(QTextBrowser):
    def __init__(self, parent):
        super(JSConsoleWidget, self).__init__(parent)

        self.setReadOnly(True)
        self.setAcceptRichText(True)
        self.setObjectName('javascriptConsole')
        self.append('<p><b>Javascript output console</b></p>')

    def showMessage(self, level, message, lineNumber, sourceId):
        sourcePath = IPFSPath(sourceId)

        if sourcePath.valid:
            source = str(sourcePath)
        else:
            source = sourceId

        if level == QWebEnginePage.InfoMessageLevel:
            levelH = 'INFO'
        elif level == QWebEnginePage.WarningMessageLevel:
            levelH = 'WARNING'
        elif level == QWebEnginePage.ErrorMessageLevel:
            levelH = 'ERROR'
        else:
            levelH = 'UNKNOWN'

        self.append('''
           <p>[{level}]
           <b>{source}</b> at line {line}: {message}
           </p>'''.format(
            source=source,
            level=levelH,
            line=lineNumber,
            message=message
        ))


class WebView(IPFSWebView):
    def __init__(self, browserTab, webProfile, enablePlugins=False,
                 parent=None):
        super(WebView, self).__init__(parent=parent)

        self.app = QCoreApplication.instance()
        self.browserTab = browserTab
        self.linkInfoTimer = QTimer()
        self.linkInfoTimer.timeout.connect(self.onLinkInfoTimeout)

        self.webPage = None
        self.changeWebProfile(webProfile)

        actionVSource = self.pageAction(QWebEnginePage.ViewSource)
        actionVSource.triggered.connect(self.onViewSource)

        self.webSettings = self.settings()
        self.webSettings.setAttribute(QWebEngineSettings.PluginsEnabled,
                                      enablePlugins)
        self.webSettings.setAttribute(QWebEngineSettings.LocalStorageEnabled,
                                      True)
        self.webSettings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        self.webSettings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)

    def createWindow(self, wintype):
        log.debug('createWindow called, wintype: {}'.format(wintype))

        # Disabled for now
        if wintype == QWebEnginePage.WebBrowserTab and 0:
            tab = self.app.mainWindow.addBrowserTab(current=False)
            return tab.webEngineView

    def onViewSource(self):
        def callback(html):
            if not html:
                return

            if self.browserTab.currentIpfsObject:
                tooltip = str(self.browserTab.currentIpfsObject)
            else:
                tooltip = self.page().url().toString()

            tab = GalacteekTab(self.app.mainWindow)
            widget = PageSourceWidget(tab)
            ensure(widget.showSource(html))
            tab.addToLayout(widget)
            self.app.mainWindow.registerTab(
                tab, 'Page source',
                current=True,
                icon=getMimeIcon('text/html'),
                tooltip=tooltip)

        self.page().toHtml(callback)

    def onJsMessage(self, level, message, lineNo, sourceId):
        self.browserTab.jsConsole.showMessage(level, message, lineNo, sourceId)

    def onLinkInfoTimeout(self):
        self.browserTab.ui.linkInfosLabel.setText('')

    def onFollowTheAtom(self, path):
        log.debug('Following atom feed: {}'.format(path))
        ensure(self.app.mainWindow.atomButton.atomFeedSubscribe(str(path)))

    def onLinkHovered(self, urlString):
        if not isinstance(urlString, str):
            return

        url = QUrl(urlString)
        if not url.isValid():
            return

        if url.isRelative() and self.browserTab.currentIpfsObject:
            ipfsPath = self.browserTab.currentIpfsObject.child(
                url.toString())
        else:
            ipfsPath = IPFSPath(urlString)

        if ipfsPath.valid:
            self.browserTab.ui.linkInfosLabel.setText(ipfsPath.fullPath)
        else:
            self.browserTab.ui.linkInfosLabel.setText(url.toString())

        if self.linkInfoTimer.isActive():
            self.linkInfoTimer.stop()

        self.linkInfoTimer.start(2200)

    def contextMenuEvent(self, event):
        # TODO: cleanup and refactoring provably

        analyzer = ResourceAnalyzer(parent=self)
        currentPage = self.page()
        contextMenuData = currentPage.contextMenuData()
        url = contextMenuData.linkUrl()
        mediaType = contextMenuData.mediaType()
        mediaUrl = contextMenuData.mediaUrl()

        if not url.isValid() and not mediaUrl.isValid():
            menu = currentPage.createStandardContextMenu()
            menu.exec(event.globalPos())
            return

        ipfsPath = IPFSPath(url.toString(), autoCidConv=True)

        if mediaType != QWebEngineContextMenuData.MediaTypeNone and mediaUrl:
            mediaIpfsPath = IPFSPath(mediaUrl.toString(), autoCidConv=True)
        else:
            mediaIpfsPath = None

        if ipfsPath.valid:
            menu = QMenu()
            menu.addAction(getIcon('clipboard.png'),
                           iCopyPathToClipboard(),
                           functools.partial(self.app.setClipboardText,
                                             str(ipfsPath)
                                             ))
            menu.addSeparator()
            menu.addAction(getIcon('open.png'), iOpen(), functools.partial(
                ensure, self.app.resourceOpener.open(ipfsPath)))
            menu.addAction(getIcon('ipfs-logo-128-black.png'),
                           iOpenInTab(),
                           functools.partial(self.openInTab, ipfsPath))
            menu.addSeparator()
            menu.addAction(getIcon('hashmarks.png'),
                           iHashmark(),
                           functools.partial(self.hashmarkPath, str(ipfsPath)))
            menu.addSeparator()
            menu.addAction(getIcon('pin.png'), iPin(),
                           functools.partial(self.browserTab.pinPath,
                                             ipfsPath.objPath))
            menu.addAction(
                getIcon('pin.png'),
                iPinRecursive(),
                functools.partial(
                    self.browserTab.pinPath,
                    ipfsPath.objPath,
                    True))

            def rscAnalyzed(fut, path, iMenu):
                try:
                    mimeType, stat = fut.result()
                except Exception:
                    pass
                else:
                    if mimeType and mimeType.isAtomFeed:
                        iMenu.addSeparator()
                        iMenu.addAction(
                            getIcon('atom-feed.png'),
                            'Follow Atom feed',
                            lambda: self.onFollowTheAtom(path)
                        )
            ensure(
                analyzer(ipfsPath),
                futcallback=lambda fut: rscAnalyzed(
                    fut,
                    ipfsPath,
                    menu
                )
            )

            menu.exec(event.globalPos())

        elif mediaIpfsPath and mediaIpfsPath.valid:
            # Needs refactor
            menu = QMenu()

            menu.addSeparator()
            menu.addAction(getIcon('clipboard.png'),
                           iCopyPathToClipboard(),
                           functools.partial(self.app.setClipboardText,
                                             str(mediaIpfsPath)
                                             ))
            menu.addSeparator()
            menu.addAction(getIcon('open.png'), iOpen(), functools.partial(
                ensure, self.app.resourceOpener.open(str(mediaIpfsPath))))
            menu.addAction(
                getIcon('ipfs-logo-128-black.png'),
                iOpenInTab(),
                functools.partial(
                    self.openInTab,
                    mediaIpfsPath))
            menu.addSeparator()
            menu.addAction(getIcon('hashmarks.png'),
                           iHashmark(),
                           functools.partial(self.hashmarkPath,
                                             str(mediaIpfsPath)))
            menu.addSeparator()
            menu.addAction(getIcon('pin.png'), iPin(),
                           functools.partial(self.browserTab.pinPath,
                                             mediaIpfsPath.objPath))
            menu.addAction(getIcon('pin.png'), iPinRecursive(),
                           functools.partial(self.browserTab.pinPath,
                                             mediaIpfsPath.objPath, True))
            menu.addSeparator()

            async def rscMenuEnable(mainMenu, path, mimeType, stat, analyzer):
                if mimeType.isImage:
                    statInfo = StatInfo(stat)

                    if statInfo.valid and statInfo.dataLargerThan(
                            megabytes(4)):
                        return

                    codes = await analyzer.decodeQrCodes(str(path))
                    if codes:
                        codesMenu = qrCodesMenuBuilder(
                            codes, self.app.resourceOpener, parent=mainMenu)
                        mainMenu.addMenu(codesMenu)

            def rscAnalyzed(fut, path, mediaType, analyzer):
                try:
                    mimeType, stat = fut.result()
                except Exception:
                    pass
                else:
                    ensure(rscMenuEnable(menu, path, mimeType, stat,
                                         analyzer))

            ensure(
                analyzer(mediaIpfsPath),
                futcallback=lambda fut: rscAnalyzed(
                    fut,
                    mediaIpfsPath,
                    mediaType,
                    analyzer
                )
            )

            menu.exec(event.globalPos())
        else:
            # Non-IPFS URL
            menu = QMenu()
            scheme = url.scheme()

            if scheme in ['http', 'https'] and \
                    self.app.settingsMgr.allowHttpBrowsing:
                menu.addAction(
                    iOpenHttpInTab(),
                    functools.partial(self.openUrlInTab, url)
                )
            elif isSchemeRegistered(scheme):
                # Non-IPFS URL but a scheme we know
                menu.addAction(
                    iOpenLinkInTab(),
                    functools.partial(self.openUrlInTab, url)
                )

            menu.exec(event.globalPos())

    def hashmarkPath(self, path):
        ipfsPath = IPFSPath(path, autoCidConv=True)
        if ipfsPath.valid:
            addHashmark(self.browserTab.app.marksLocal,
                        ipfsPath.fullPath,
                        ipfsPath.basename if ipfsPath.basename else iUnknown())

    def openInTab(self, path):
        tab = self.browserTab.gWindow.addBrowserTab()
        tab.browseFsPath(path)

    def openUrlInTab(self, url):
        tab = self.browserTab.gWindow.addBrowserTab()
        tab.enterUrl(url)

    def downloadLink(self, menudata):
        url = menudata.linkUrl()
        self.page().download(url, None)

    def installPage(self):
        if self.webPage:
            del self.webPage

        self.webPage = CustomWebPage(self.webProfile, self)
        self.webPage.jsConsoleMessage.connect(self.onJsMessage)
        self.webPage.linkHovered.connect(self.onLinkHovered)
        self.setPage(self.webPage)

    def changeWebProfile(self, profile):
        self.webProfile = profile
        self.installPage()


class BrowserKeyFilter(QObject):
    hashmarkPressed = pyqtSignal()
    savePagePressed = pyqtSignal()
    reloadPressed = pyqtSignal()
    reloadFullPressed = pyqtSignal()
    zoominPressed = pyqtSignal()
    zoomoutPressed = pyqtSignal()
    focusUrlPressed = pyqtSignal()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            modifiers = event.modifiers()
            key = event.key()

            if modifiers & Qt.ControlModifier:
                if key == Qt.Key_B:
                    self.hashmarkPressed.emit()
                    return True
                if key == Qt.Key_S:
                    self.savePagePressed.emit()
                    return True
                if key == Qt.Key_R:
                    self.reloadPressed.emit()
                    return True
                if key == Qt.Key_F5:
                    self.reloadFullPressed.emit()
                    return True
                if key == Qt.Key_L:
                    self.focusUrlPressed.emit()
                    return True
                if key == Qt.Key_Plus:
                    self.zoominPressed.emit()
                    return True
                if key == Qt.Key_Minus:
                    self.zoomoutPressed.emit()
                    return True

            if key == Qt.Key_F5:
                self.reloadPressed.emit()
                return True

        return False


class URLInputWidget(QLineEdit):
    def __init__(self, history, historyView, parent):
        super(URLInputWidget, self).__init__(parent)

        self.app = QCoreApplication.instance()
        self.history = history
        self.historyMatches = historyView
        self.browser = parent

        self.setObjectName('urlZone')
        self.setMinimumWidth(400)
        self.setDragEnabled(True)
        self.setMaxLength(1024)

        self.urlEditing = False
        self.urlInput = None

        self.editTimer = QTimer(self)
        self.editTimer.timeout.connect(self.onTimeoutUrlEdit)
        self.editTimer.setSingleShot(True)

        self.returnPressed.connect(self.onReturnPressed)
        self.historyMatches.historyItemSelected.connect(
            self.onHistoryItemSelected)
        self.historyMatches.collapsed.connect(
            self.onHistoryCollapse)
        self.textEdited.connect(self.onUrlUserEdit)

    @property
    def editTimeoutMs(self):
        timeout = self.app.settingsMgr.urlHistoryEditTimeout
        return timeout if isinstance(timeout, int) else 1000

    def unfocus(self):
        self.urlEditing = False
        self.clearFocus()

    def cancelTimer(self):
        self.editTimer.stop()

    def hideMatches(self):
        self.historyMatches.hide()

    def onReturnPressed(self):
        self.urlEditing = False
        self.unfocus()
        self.browser.handleEditedUrl(self.text())

    def onHistoryCollapse(self):
        self.setFocus(Qt.PopupFocusReason)
        self.deselect()

    def focusInEvent(self, event):
        if event.reason() in [Qt.ShortcutFocusReason, Qt.MouseFocusReason,
                              Qt.PopupFocusReason, Qt.ActiveWindowFocusReason,
                              Qt.TabFocusReason]:
            self.urlEditing = True

        super(URLInputWidget, self).focusInEvent(event)

    def focusOutEvent(self, event):
        if event.reason() not in [
                Qt.ActiveWindowFocusReason,
                Qt.PopupFocusReason,
                Qt.TabFocusReason,
                Qt.OtherFocusReason]:
            self.urlEditing = False
            self.editTimer.stop()

        super(URLInputWidget, self).focusOutEvent(event)

    def onUrlUserEdit(self, text):
        self.urlInput = text

        if not self.urlEditing:
            return

        if not self.editTimer.isActive():
            self.editTimer.start(self.editTimeoutMs)
        else:
            self.editTimer.stop()
            self.editTimer.start(self.editTimeoutMs)

    def onTimeoutUrlEdit(self):
        ensure(self.historyLookup())

    async def historyLookup(self):
        if self.urlInput:
            markMatches = []
            result = list(self.app.marksLocal.searchAllByMetadata({
                'title': self.urlInput,
                'description': self.urlInput
            }))

            for mark in result:
                try:
                    markMatches.append({
                        'title': mark.markData['metadata']['title'],
                        'url': IPFSPath(mark.path).ipfsUrl
                    })
                except Exception:
                    continue

            hMatches = await self.history.match(self.urlInput)

            if len(markMatches) > 0 or len(hMatches) > 0:
                self.historyMatches.showMatches(markMatches, hMatches)
                self.historyMatches.show()
                self.historyMatches.setFocus(Qt.OtherFocusReason)

            self.editTimer.stop()

    def onHistoryItemSelected(self, urlStr):
        self.historyMatches.hide()
        self.urlEditing = False

        url = QUrl(urlStr)

        if url.isValid():
            self.browser.enterUrl(url)


class CIDInfosDisplay(QObject):
    objectVisited = pyqtSignal(IPFSPath)

    tooltipMessage = '''
        <p>
            <img src='{icon}' width='32' height='32'/>
        </p>
        <p>Root CID: CIDv{cidv} {more} <b>{cid}</b></p>
    '''

    def __init__(self, label, parent=None):
        super(CIDInfosDisplay, self).__init__(parent)

        self.cidLabel = label
        self.objectVisited.connect(self.onVisited)

        self.pathCubeOrange = ':/share/icons/cube-nova-orange.png'
        self.pathCubeAqua = ':/share/icons/cube-nova-aqua.png'

        self.pixmapCubeOrange = QPixmap.fromImage(QImage(self.pathCubeOrange))
        self.pixmapCubeAqua = QPixmap.fromImage(QImage(self.pathCubeAqua))

    def onVisited(self, ipfsPath):
        cidRepr = ipfsPath.rootCidRepr

        if ipfsPath.rootCidUseB32:
            self.cidLabel.setPixmap(
                self.pixmapCubeOrange.scaled(16, 16))
            self.cidLabel.setToolTip(self.tooltipMessage.format(
                cid=cidRepr, cidv=1, more='(base32)',
                icon=self.pathCubeOrange))
        else:
            self.cidLabel.setPixmap(
                self.pixmapCubeAqua.scaled(16, 16))

            if not ipfsPath.rootCid:
                return

            self.cidLabel.setToolTip(self.tooltipMessage.format(
                cid=cidRepr, cidv=ipfsPath.rootCid.version, more='',
                icon=self.pathCubeAqua))


class BrowserTab(GalacteekTab):
    # signals
    ipfsObjectVisited = pyqtSignal(IPFSPath)

    def __init__(self, gWindow, pinBrowsed=False):
        super(BrowserTab, self).__init__(gWindow)

        self.browserWidget = QWidget(self)
        self.browserWidget.setAttribute(Qt.WA_DeleteOnClose)

        self.jsConsoleWidget = JSConsoleWidget(self)
        self.jsConsoleWidget.setMaximumHeight(180)
        self.jsConsoleWidget.hide()

        self.ui = ui_browsertab.Ui_BrowserTabForm()
        self.ui.setupUi(self.browserWidget)

        self.vLayout.addWidget(self.browserWidget)
        self.ui.vLayoutConsole.addWidget(self.jsConsoleWidget)

        # URL zone
        self.historySearches = HistoryMatchesWidget(parent=self)
        self.historySearches.hide()
        self.urlZone = URLInputWidget(self.history, self.historySearches, self)
        self.ui.layoutHistory.addWidget(self.historySearches)
        self.ui.layoutUrl.addWidget(self.urlZone)

        self.cidInfosDisplay = CIDInfosDisplay(self.ui.cidInfoLabel,
                                               parent=self)

        initialProfileName = self.app.settingsMgr.defaultWebProfile
        if initialProfileName not in self.app.availableWebProfilesNames():
            initialProfileName = WP_NAME_MINIMAL

        webProfile = self.getWebProfileByName(initialProfileName)

        self.webEngineView = WebView(
            self, webProfile,
            enablePlugins=self.app.settingsMgr.ppApiPlugins,
            parent=self
        )
        self.ui.vLayoutBrowser.addWidget(self.webEngineView)

        self.webEngineView.urlChanged.connect(self.onUrlChanged)
        self.webEngineView.loadFinished.connect(self.onLoadFinished)
        self.webEngineView.iconChanged.connect(self.onIconChanged)
        self.webEngineView.loadProgress.connect(self.onLoadProgress)
        self.webEngineView.titleChanged.connect(self.onTitleChanged)

        self.ui.backButton.clicked.connect(self.backButtonClicked)
        self.ui.forwardButton.clicked.connect(self.forwardButtonClicked)

        self.ui.reloadPageButton.clicked.connect(self.refreshButtonClicked)
        self.ui.stopButton.clicked.connect(self.stopButtonClicked)

        self.ui.backButton.setEnabled(False)
        self.ui.forwardButton.setEnabled(False)
        self.ui.stopButton.setEnabled(False)

        self.ui.linkInfosLabel.setObjectName('linkInfos')

        # Save page button, visible when non-IPFS content is displayed
        saveIcon = getMimeIcon('text/html')
        self.savePageButton = PopupToolButton(
            saveIcon, mode=QToolButton.InstantPopup, parent=self
        )
        self.savePageButton.setToolTip(iSaveWebPage())
        self.savePageButton.menu.addAction(saveIcon,
                                           iSaveWebPage(),
                                           self.onSavePage)
        self.savePageButton.setEnabled(False)

        self.hashmarkPageAction = QAction(getIcon('hashmark-black.png'),
                                          iHashmarkThisPage(), self,
                                          shortcut=QKeySequence('Ctrl+b'),
                                          triggered=self.onHashmarkPage)
        self.ui.hashmarkThisPage.setDefaultAction(self.hashmarkPageAction)
        self.ui.hashmarkThisPage.setEnabled(False)

        self.ui.hLayoutCtrl.addWidget(self.savePageButton)

        # Setup the IPFS control tool button (has actions
        # for browsing CIDS and web profiles etc..)

        self.ipfsControlMenu = QMenu()
        self.webProfilesMenu = QMenu('Web profile')

        self.webProfilesGroup = QActionGroup(self.webProfilesMenu)
        self.webProfilesGroup.setExclusive(True)
        self.webProfilesGroup.triggered.connect(self.onWebProfileSelected)

        self.webProMinAction = QAction(WP_NAME_MINIMAL, self)
        self.webProMinAction.setCheckable(True)
        self.webProIpfsAction = QAction(WP_NAME_IPFS, self)
        self.webProIpfsAction.setCheckable(True)
        self.webProWeb3Action = QAction(WP_NAME_WEB3, self)
        self.webProWeb3Action.setCheckable(True)

        self.webProfilesGroup.addAction(self.webProMinAction)
        self.webProfilesGroup.addAction(self.webProIpfsAction)
        self.webProfilesGroup.addAction(self.webProWeb3Action)

        for action in self.webProfilesGroup.actions():
            self.webProfilesMenu.addAction(action)

        self.checkWebProfileByName(initialProfileName)

        self.ipfsControlMenu.addMenu(self.webProfilesMenu)
        self.ipfsControlMenu.addSeparator()

        self.loadIpfsCIDAction = QAction(getIconIpfsIce(),
                                         iBrowseIpfsCID(), self,
                                         triggered=self.onLoadIpfsCID)
        self.loadIpfsMultipleCIDAction = QAction(
            getIconIpfsIce(),
            iBrowseIpfsMultipleCID(),
            self,
            triggered=self.onLoadIpfsMultipleCID)
        self.loadIpnsAction = QAction(getIconIpfsWhite(),
                                      iBrowseIpnsHash(), self,
                                      triggered=self.onLoadIpns)
        self.followIpnsAction = QAction(getIconIpfsWhite(),
                                        iFollow(), self,
                                        triggered=self.onFollowIpns)
        self.loadHomeAction = QAction(getIcon('go-home.png'),
                                      iBrowseHomePage(), self,
                                      triggered=self.onLoadHome)

        self.jsConsoleAction = QAction(getIcon('terminal.png'),
                                       iJsConsole(), self,
                                       shortcut=QKeySequence('Ctrl+x'))
        self.jsConsoleAction.setCheckable(True)
        self.jsConsoleAction.toggled.connect(self.onJsConsoleToggle)

        self.mapPathAction = QAction(getIconIpfsIce(),
                                     iCreateQaMapping(), self,
                                     triggered=self.onCreateMapping)

        self.loadFromCbAction = QAction(
            getIcon('clipboard.png'),
            iBrowseCurrentClipItem(), self,
            triggered=self.onBrowseCurrentClipItem
        )

        self.followIpnsAction.setEnabled(False)

        self.ipfsControlMenu.addAction(self.jsConsoleAction)
        self.ipfsControlMenu.addSeparator()
        self.ipfsControlMenu.addAction(self.mapPathAction)
        self.ipfsControlMenu.addSeparator()
        self.ipfsControlMenu.addAction(self.loadFromCbAction)
        self.ipfsControlMenu.addAction(self.loadIpfsCIDAction)
        self.ipfsControlMenu.addAction(self.loadIpfsMultipleCIDAction)
        self.ipfsControlMenu.addAction(self.loadIpnsAction)
        self.ipfsControlMenu.addAction(self.followIpnsAction)
        self.ipfsControlMenu.addAction(self.loadHomeAction)

        self.ui.loadIpfsButton.setMenu(self.ipfsControlMenu)
        self.ui.loadIpfsButton.setPopupMode(QToolButton.InstantPopup)
        self.ui.loadIpfsButton.clicked.connect(self.onLoadIpfsCID)

        self.ui.pBarBrowser.setTextVisible(False)
        self.ui.pinAllButton.setCheckable(True)
        self.ui.pinAllButton.setAutoRaise(True)

        if pinBrowsed:
            self.ui.pinAllButton.setChecked(True)
        else:
            self.ui.pinAllButton.setChecked(self.gWindow.pinAllGlobalChecked)

        self.ui.pinAllButton.toggled.connect(self.onToggledPinAll)

        # PIN tool button
        iconPin = getIcon('pin.png')

        pinMenu = QMenu()
        pinMenu.addAction(iconPin, iPinThisPage(), self.onPinSingle)
        pinMenu.addAction(iconPin, iPinRecursive(), self.onPinRecursive)
        pinMenu.addSeparator()
        pinMenu.addAction(iconPin, iPinRecursiveParent(),
                          self.onPinRecursiveParent)
        pinMenu.addSeparator()
        pinMenu.addAction(iconPin, iPinPageLinks(), self.onPinPageLinks)

        self.ui.pinToolButton.setMenu(pinMenu)
        self.ui.pinToolButton.setIcon(iconPin)
        self.ui.pinToolButton.setText(iPin())

        self.ui.zoomInButton.clicked.connect(self.onZoomIn)
        self.ui.zoomOutButton.clicked.connect(self.onZoomOut)

        # Event filter
        evfilter = BrowserKeyFilter(self)
        evfilter.hashmarkPressed.connect(self.onHashmarkPage)
        evfilter.reloadPressed.connect(self.onReloadPage)
        evfilter.reloadFullPressed.connect(self.onReloadPageNoCache)
        evfilter.zoominPressed.connect(self.onZoomIn)
        evfilter.zoomoutPressed.connect(self.onZoomOut)
        evfilter.focusUrlPressed.connect(self.onFocusUrl)
        self.installEventFilter(evfilter)

        self.resolveTimer = QTimer(self)
        self.resolveTimerEnsMs = 7000
        self.urlInput = None

        self.app.clipTracker.clipboardPathProcessed.connect(
            self.onClipboardIpfs)
        self.ipfsObjectVisited.connect(self.onPathVisited)

        self._currentIpfsObject = None
        self._currentUrl = None
        self.currentPageTitle = None

    @property
    def history(self):
        return self.gWindow.app.urlHistory

    @property
    def webView(self):
        return self.webEngineView

    @property
    def currentUrl(self):
        return self._currentUrl

    @property
    def currentUrlHasFileName(self):
        if self.currentUrl:
            return self.currentUrl.fileName() != ''

    @property
    def jsConsole(self):
        return self.jsConsoleWidget

    @property
    def tabPage(self):
        return self.gWindow.tabWidget.widget(self.tabPageIdx)

    @property
    def tabPageIdx(self):
        return self.gWindow.tabWidget.indexOf(self)

    @property
    def gatewayAuthority(self):
        return self.app.gatewayAuthority

    @property
    def gatewayUrl(self):
        return self.app.gatewayUrl

    @property
    def pinAll(self):
        return self.ui.pinAllButton.isChecked()

    @property
    def currentIpfsObject(self):
        return self._currentIpfsObject

    def installCustomPageScripts(self, handler, url):
        # Page-specific IPFS scripts

        if url.scheme() == SCHEME_IPFS:
            rootCid = None

            if issubclass(handler.__class__, DAGProxySchemeHandler):
                if handler.proxied:
                    rootCid = handler.proxied.dagCid
            elif issubclass(handler.__class__, MultiDAGProxySchemeHandler):
                if len(handler.proxied) > 0:
                    rootCid = handler.proxied[0].dagCid
            else:
                rootCid = url.host()

            if not rootCid:
                return

            scripts = self.webEngineView.webPage.scripts()

            script = scriptFromString('rootcid', '''
                window.rootcid = '{cid}';
            '''.format(cid=rootCid))

            existing = scripts.findScript('rootcid')
            if existing:
                scripts.remove(existing)

            scripts.insert(script)

    def onPathVisited(self, ipfsPath):
        # Called after a new IPFS object has been loaded in this tab

        if ipfsPath.valid:
            self.cidInfosDisplay.objectVisited.emit(ipfsPath)
            ensure(self.tsVisitPath(ipfsPath.objPath))

    @ipfsStatOp
    async def tsVisitPath(self, ipfsop, path, stat):
        # If automatic pinning is checked we pin the object
        if self.pinAll is True:
            self.pinPath(path, recursive=False, notify=False)

    def changeWebProfileByName(self, wpName):
        if self.webEngineView.webProfile.profileName == wpName:
            log.debug('Profile {p} already set'.format(p=wpName))
            return

        self.checkWebProfileByName(wpName)

    def checkWebProfileByName(self, wpName):
        if wpName == WP_NAME_MINIMAL:
            self.webProMinAction.setChecked(True)
        elif wpName == WP_NAME_IPFS:
            self.webProIpfsAction.setChecked(True)
        elif wpName == WP_NAME_WEB3:
            self.webProWeb3Action.setChecked(True)

    def getWebProfileByName(self, wpName, fallback=WP_NAME_MINIMAL):
        return self.app.webProfiles.get(
            wpName, self.app.webProfiles[fallback])

    def onWebProfileSelected(self, action):
        if self.webEngineView.webProfile.profileName == action.text():
            log.debug('Profile {p} already set'.format(p=action.text()))
            return

        url = self.currentUrl

        if action is self.webProMinAction:
            self.webEngineView.changeWebProfile(
                self.getWebProfileByName(WP_NAME_MINIMAL)
            )
        elif action is self.webProIpfsAction:
            self.webEngineView.changeWebProfile(
                self.getWebProfileByName(WP_NAME_IPFS)
            )
        elif action is self.webProWeb3Action:
            self.webEngineView.changeWebProfile(
                self.getWebProfileByName(WP_NAME_WEB3)
            )

        if url:
            # Reload page
            self.enterUrl(url)
        else:
            async def showProfileChangedPage():
                pName = self.webEngineView.webProfile.profileName
                body = await renderTemplate(
                    'profilechanged.html',
                    webProfile=pName,
                    title='Web profile changed to {name}'.format(name=pName)
                )
                self.webEngineView.webPage.setHtml(
                    body, QUrl('z:/profilechanged.html'))

            ensure(showProfileChangedPage())

    def onJsConsoleToggle(self, checked):
        self.jsConsoleWidget.setVisible(checked)

    def onCreateMapping(self):
        if not self.currentIpfsObject:
            return messageBox(iNotAnIpfsResource())

        runDialog(QSchemeCreateMappingDialog, self.currentIpfsObject)

    def onClipboardIpfs(self, pathObj):
        pass

    def onToggledPinAll(self, checked):
        pass

    def onFocusUrl(self):
        self.focusUrlZone(True, reason=Qt.ShortcutFocusReason)

    def focusUrlZone(self, select=False, reason=Qt.OtherFocusReason):
        self.urlZone.setFocus(reason)

        if select:
            self.urlZone.setSelection(0, len(self.urlZone.text()))

        self.urlZone.urlEditing = True

    def onReloadPage(self):
        self.reloadPage()

    def onReloadPageNoCache(self):
        self.reloadPage(bypassCache=True)

    def reloadPage(self, bypassCache=False):
        self.urlZone.unfocus()
        self.webEngineView.triggerPageAction(
            QWebEnginePage.ReloadAndBypassCache if bypassCache is True else
            QWebEnginePage.Reload
        )

    def onSavePage(self):
        tmpd = self.app.tempDirCreate(self.app.tempDirWeb)
        if tmpd is None:
            return messageBox('Cannot create temporary directory')

        page = self.webView.page()

        url = page.url()
        filename = url.fileName()

        if not filename or cidValid(filename):
            filename = 'index.html'

        path = os.path.join(tmpd, filename)
        page.save(path, QWebEngineDownloadItem.CompleteHtmlSaveFormat)

    def onHashmarkPage(self):
        if self.currentIpfsObject and self.currentIpfsObject.valid:
            addHashmark(self.app.marksLocal,
                        self.currentIpfsObject.fullPath,
                        self.currentPageTitle,
                        stats=self.app.ipfsCtx.objectStats.get(
                            self.currentIpfsObject.path, {}))
        else:
            messageBox(iNotAnIpfsResource())

    def onPinResult(self, f):
        try:
            path, code, msg = f.result()
        except:
            pass
        else:
            path = IPFSPath(path)
            if not path.valid:
                log.debug('Invalid path in pin result: {}'.format(str(path)))
                return

            if code == 0:
                self.app.systemTrayMessage('PIN', iPinSuccess(str(path)),
                                           timeout=2000)
            elif code == 1:
                self.app.systemTrayMessage('PIN', iPinError(str(path), msg),
                                           timeout=3000)
            elif code == 2:
                # Cancelled, no need to notify here
                pass
            else:
                log.debug('Unknown status code for pinning result')

    @ipfsOp
    async def pinQueuePath(self, ipfsop, path, recursive, notify):
        log.debug('Pinning object {0} (recursive: {1})'.format(path,
                                                               recursive))
        onSuccess = None
        if notify is True:
            onSuccess = self.onPinResult
        await ipfsop.ctx.pinner.queue(path, recursive, onSuccess,
                                      qname='browser')

    def pinPath(self, path, recursive=True, notify=True):
        if isinstance(path, str):
            ensure(self.pinQueuePath(path, recursive, notify))
        elif isinstance(path, IPFSPath):
            ensure(self.pinQueuePath(path.objPath, recursive, notify))

    def printButtonClicked(self):
        # TODO: reinstate the printing button
        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        dialog.setModal(True)

        def success(ok):
            return ok

        if dialog.exec_() == QDialog.Accepted:
            currentPage = self.webEngineView.page()
            currentPage.print(printer, success)

    def onPinSingle(self):
        if not self.currentIpfsObject:
            return messageBox(iNotAnIpfsResource())

        self.pinPath(self.currentIpfsObject.objPath, recursive=False)

    def onPinRecursive(self):
        if not self.currentIpfsObject:
            return messageBox(iNotAnIpfsResource())

        self.pinPath(self.currentIpfsObject.objPath, recursive=True)

    def onPinRecursiveParent(self):
        if not self.currentIpfsObject:
            return messageBox(iNotAnIpfsResource())

        if self.currentUrlHasFileName:
            parent = self.currentIpfsObject.parent()
            self.pinPath(parent.objPath, recursive=True)
        else:
            self.pinPath(self.currentIpfsObject.objPath, recursive=True)

    def onPinPageLinks(self):
        if not self.currentIpfsObject:
            return messageBox(iNotAnIpfsResource())

        def htmlReady(htmlCode):
            ensure(self.pinIpfsLinksInPage(htmlCode))

        self.webEngineView.webPage.toHtml(htmlReady)

    @ipfsOp
    async def pinIpfsLinksInPage(self, ipfsop, htmlCode):
        if not isinstance(htmlCode, str):
            return

        baseUrl = self.currentUrl.url(
            QUrl.RemoveFilename | QUrl.RemoveFragment | QUrl.RemoveQuery)
        basePath = IPFSPath(baseUrl)

        if not basePath.valid:
            return

        # Being a potentially CPU-intensive task for large documents, run
        # the HTML parser in the threadpool executor

        parser = IPFSLinksParser(basePath)
        await self.app.loop.run_in_executor(self.app.executor,
                                            parser.feed, htmlCode)

        tab = PinBatchTab(self.app.mainWindow)
        bulkWidget = PinBatchWidget(basePath, parser.links, parent=tab)
        tab.addToLayout(bulkWidget)
        self.app.mainWindow.registerTab(tab, 'Pin batch', current=True,
                                        icon=getIcon('pin.png'))

    def onBrowseCurrentClipItem(self):
        current = self.app.clipTracker.getCurrent()
        if current:
            self.browseFsPath(IPFSPath(current.fullPath))
        else:
            messageBox(iClipboardEmpty())

    def onLoadIpfsCID(self):
        def onValidated(d):
            path = IPFSPath(d.getHash(), autoCidConv=True)
            if path.valid:
                self.browseFsPath(path)

        runDialog(IPFSCIDInputDialog, title=iEnterIpfsCIDDialog(),
                  accepted=onValidated)

    def onLoadIpfsMultipleCID(self):
        def onValidated(dlg):
            # Open a tab for every CID
            cids = dlg.getCIDs()
            for cid in cids:
                path = IPFSPath(cid, autoCidConv=True)
                if not path.valid:
                    continue
                self.gWindow.addBrowserTab().browseFsPath(path)

        runDialog(IPFSMultipleCIDInputDialog,
                  title=iEnterIpfsCIDDialog(),
                  accepted=onValidated)

    def onLoadIpns(self):
        text, ok = QInputDialog.getText(self,
                                        iEnterIpnsDialog(),
                                        iEnterIpns())
        if ok:
            self.browseIpnsKey(text)

    def onFollowIpns(self):
        if self.currentIpfsObject:
            runDialog(AddFeedDialog, self.app.marksLocal,
                      self.currentIpfsObject.objPath,
                      title=iFollowIpnsDialog())

    def onLoadHome(self):
        self.loadHomePage()

    def loadHomePage(self):
        homeUrl = self.app.settingsMgr.getSetting(CFG_SECTION_BROWSER,
                                                  CFG_KEY_HOMEURL)
        self.enterUrl(QUrl(homeUrl))

    def refreshButtonClicked(self):
        self.webEngineView.reload()

    def stopButtonClicked(self):
        self.webEngineView.stop()
        self.ui.pBarBrowser.setValue(0)
        self.ui.stopButton.setEnabled(False)

    def backButtonClicked(self):
        self.urlZone.unfocus()
        currentPage = self.webEngineView.page()
        currentPage.history().back()

    def forwardButtonClicked(self):
        self.urlZone.unfocus()
        currentPage = self.webEngineView.page()
        currentPage.history().forward()

    def onUrlChanged(self, url):
        if not url.isValid() or url.scheme() in ['data', SCHEME_Z]:
            return

        if url.scheme() in [SCHEME_IPFS, SCHEME_IPNS]:
            # ipfs:// or ipns://
            self.urlZone.setStyleSheet('''
                QLineEdit {
                    background-color: #C3D7DF;
                }''')

            self.urlZone.clear()
            self.urlZone.insert(url.toString())
            self._currentIpfsObject = IPFSPath(url.toString())
            self._currentUrl = url
            self.ipfsObjectVisited.emit(self.currentIpfsObject)
            self.ui.hashmarkThisPage.setEnabled(True)
            self.ui.pinToolButton.setEnabled(True)

            self.followIpnsAction.setEnabled(
                self.currentIpfsObject.isIpnsRoot)

        elif url.authority() == self.gatewayAuthority:
            # dweb:/ with IPFS gateway's authority
            # Content loaded from IPFS gateway, this is IPFS content
            urlString = url.toDisplayString(
                QUrl.RemoveAuthority | QUrl.RemoveScheme)

            self._currentIpfsObject = IPFSPath(urlString)

            if self.currentIpfsObject.valid:
                log.debug('Current IPFS object: {0}'.format(
                    repr(self.currentIpfsObject)))

                url = QUrl(self.currentIpfsObject.dwebUrl)
                self.urlZone.clear()
                self.urlZone.insert(url.toString())

                self.ui.hashmarkThisPage.setEnabled(True)
                self.ui.pinToolButton.setEnabled(True)

                self.ipfsObjectVisited.emit(self.currentIpfsObject)

                self._currentUrl = url
            else:
                log.debug('Invalid IPFS path: {0}'.format(urlString))

            # Activate the follow action if this is a root IPNS address
            self.followIpnsAction.setEnabled(
                self.currentIpfsObject.isIpnsRoot)
        else:
            self._currentIpfsObject = None
            self.urlZone.clear()
            self.urlZone.insert(url.toString())
            self._currentUrl = url
            self.followIpnsAction.setEnabled(False)

        if url.scheme() in [SCHEME_ENS]:
            self.history.record(url.toString(), None)

        currentPage = self.webView.page()

        if currentPage:
            history = currentPage.history()
            self.ui.backButton.setEnabled(history.canGoBack())
            self.ui.forwardButton.setEnabled(history.canGoForward())

    def onTitleChanged(self, pageTitle):
        if pageTitle.startswith(self.gatewayAuthority):
            pageTitle = iNoTitle()

        self.currentPageTitle = pageTitle

        lenMax = 16
        if len(pageTitle) > lenMax:
            pageTitle = '{0} ...'.format(pageTitle[0:lenMax])

        idx = self.gWindow.tabWidget.indexOf(self)
        self.gWindow.tabWidget.setTabText(idx, pageTitle)
        self.gWindow.tabWidget.setTabToolTip(idx, self.currentPageTitle)

        if self.currentPageTitle != iNoTitle() and self.currentUrl and \
                self.currentUrl.isValid():
            if isSchemeRegistered(self.currentUrl.scheme()):
                self.history.record(self.currentUrl.toString(),
                                    self.currentPageTitle)

    def onLoadFinished(self, ok):
        self.ui.stopButton.setEnabled(False)
        self.savePageButton.setEnabled(True)

    def onIconChanged(self, icon):
        self.gWindow.tabWidget.setTabIcon(self.tabPageIdx, icon)

    def onLoadProgress(self, progress):
        self.ui.pBarBrowser.setValue(progress)
        self.ui.stopButton.setEnabled(progress >= 0 and progress < 100)

        if progress == 100:
            self.ui.pBarBrowser.setStyleSheet(
                '''QProgressBar::chunk#pBarBrowser {
                    background-color: #244e66;
                }''')
            self.loop.call_later(
                1,
                self.ui.pBarBrowser.setStyleSheet,
                '''QProgressBar::chunk#pBarBrowser {
                    background-color: transparent;
                }''')
        else:
            self.ui.pBarBrowser.setStyleSheet(
                '''QProgressBar::chunk#pBarBrowser {
                    background-color: #7f8491;
                }''')

    def browseFsPath(self, path):
        def _handle(iPath):
            if iPath.valid:
                self.enterUrl(QUrl(iPath.ipfsUrl))
            else:
                messageBox(iInvalidObjectPath(iPath.fullPath))

        if isinstance(path, str):
            ipfsPath = IPFSPath(path, autoCidConv=True)
            return _handle(ipfsPath)
        elif isinstance(path, IPFSPath):
            return _handle(path)

    def browseIpfsHash(self, ipfsHash):
        if not cidhelpers.cidValid(ipfsHash):
            return messageBox(iInvalidCID(ipfsHash))

        self.browseFsPath(IPFSPath(joinIpfs(ipfsHash), autoCidConv=True))

    def browseIpnsKey(self, ipnsHash):
        self.browseFsPath(IPFSPath(joinIpns(ipnsHash)))

    def enterUrl(self, url):
        self.urlZone.hideMatches()
        self.urlZone.cancelTimer()

        if not url.isValid() or url.scheme() in ['data', SCHEME_Z]:
            messageBox('Invalid URL: {0}'.format(url.toString()))
            return

        self.urlZone.urlEditing = False
        self.urlZone.clearFocus()

        self.savePageButton.setEnabled(False)
        log.debug('Entering URL {}'.format(url.toString()))

        handler = self.webEngineView.webProfile.urlSchemeHandler(
            url.scheme().encode())

        def onEnsTimeout():
            pass

        # This should not be necessary starting with qt 5.13
        if not url.path():
            url.setPath('/')

        if url.scheme() == SCHEME_ENS:
            self.resolveTimer.timeout.connect(onEnsTimeout)
            self.resolveTimer.start(self.resolveTimerEnsMs)

        if handler:
            if hasattr(handler, 'webProfileNeeded'):
                wpName = handler.webProfileNeeded
                if self.webEngineView.webProfile.profileName != wpName and \
                        wpName in self.app.webProfiles:
                    self.changeWebProfileByName(wpName)

        self.urlZone.clear()
        self.urlZone.insert(url.toString())
        self.webEngineView.load(url)

    def handleEditedUrl(self, inputStr):
        self.urlZone.hideMatches()
        self.urlZone.cancelTimer()
        self.urlZone.unfocus()

        #
        # Handle seamless upgrade of CIDv0, suggested by @lidel
        #
        # If the user uses the native scheme (ipfs://) but passes
        # a base58-encoded CID as host (whatever the version),
        # convert it to base32 with cidhelpers.cidConvertBase32()
        # and replace the old CID in the URL
        #
        # https://github.com/eversum/galacteek/issues/5
        #

        if inputStr.startswith('ipfs://'):
            # Home run
            match = cidhelpers.ipfsDedSearchPath58(inputStr)
            if match:
                rootcid = match.group('rootcid')
                if rootcid and re.search('[A-Z]', rootcid):
                    # Has uppercase characters .. Either CIDv0
                    # or base58-encoded CIDv1
                    # If the conversion to base32 is successfull,
                    # replace the base58-encoded CID in the URL with
                    # the base32-encoded CIDv1

                    multihash = cidhelpers.cidConvertBase32(rootcid)
                    if multihash:
                        inputStr = re.sub(rootcid, multihash, inputStr,
                                          count=1)
                    else:
                        return messageBox(iInvalidCID(rootcid))
            else:
                return messageBox(iInvalidUrl(inputStr))

        url = QUrl(inputStr)
        if not url.isValid() or not url.scheme():
            # Invalid URL or no scheme given
            # If the address bar contains a valid CID or IPFS path, load it
            iPath = IPFSPath(inputStr, autoCidConv=True)

            if iPath.valid:
                return self.browseFsPath(iPath)
            else:
                return messageBox(iInvalidUrl(inputStr))

        scheme = url.scheme()

        if isSchemeRegistered(scheme):
            self.enterUrl(url)
        elif scheme in ['http', 'https'] and \
                self.app.settingsMgr.allowHttpBrowsing is True:
            # Browse http urls if allowed
            self.enterUrl(url)
        else:
            messageBox('Unknown URL type')

    def onEnsResolved(self, domain, path):
        logUser.info('ENS: {0} maps to {1}'.format(domain, path))

    def onZoomIn(self):
        cFactor = self.webView.zoomFactor()
        self.webView.setZoomFactor(cFactor + 0.25)

    def onZoomOut(self):
        cFactor = self.webView.zoomFactor()
        self.webView.setZoomFactor(cFactor - 0.25)
