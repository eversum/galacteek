from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEnginePage
from PyQt5.QtWebEngineWidgets import QWebEngineSettings
from PyQt5.QtWebChannel import QWebChannel

from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal
from PyQt5.QtCore import QJsonValue, QVariant, QUrl
from PyQt5.QtCore import QTimer

from PyQt5.QtWidgets import QApplication

from galacteek.ui.widgets import GalacteekTab
from galacteek import ensure
from galacteek import log
from galacteek.dweb.render import renderTemplate
from galacteek.dweb.webscripts import ipfsClientScripts
from galacteek.dweb.webscripts import orbitScripts
from galacteek.dweb.webscripts import ethereumClientScripts


class BaseHandler(QObject):
    def __init__(self, parent):
        super().__init__(parent)

    @pyqtSlot()
    def test(self):
        pass


class GalacteekHandler(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.app = QApplication.instance()

    @pyqtSlot(str)
    def openResource(self, path):
        ensure(self.app.resourceOpener.open(path))

    @pyqtSlot(str)
    def openIpfsLink(self, path):
        tab = self.app.mainWindow.addBrowserTab()
        tab.browseFsPath(path)

    @pyqtSlot(str)
    def copyToClipboard(self, path):
        if len(path) > 1024:
            return

        self.app.setClipboardText(path)

    @pyqtSlot(str)
    def explorePath(self, path):
        if len(path) > 1024:
            return

        self.app.mainWindow.explore(path)


class BasePage(QWebEnginePage):
    def __init__(self, template, url=None, parent=None):
        super(BasePage, self).__init__(parent)
        self.app = QApplication.instance()
        self.template = template
        self._handlers = {}
        self.pageCtx = {}
        self.channel = QWebChannel()
        self.url = url if url else QUrl('qrc:/')
        self.setUrl(self.url)
        self.setWebChannel(self.channel)
        self.webScripts = self.profile().scripts()

        self.settings().setAttribute(
            QWebEngineSettings.LocalStorageEnabled,
            True)
        self.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls,
            True)
        self.installScripts()
        ensure(self.render())

    def installScripts(self):
        pass

    def register(self, name, obj):
        self.channel.registerObject(name, obj)
        self._handlers[name] = obj

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        log.debug(
            'JS: level: {0}, source: {1}, line: {2}, message: {3}'.format(
                level,
                sourceId,
                lineNumber,
                message))

    async def render(self):
        self.setHtml(await renderTemplate(self.template, **self.pageCtx),
                     baseUrl=self.url)


class IPFSPage(BasePage):
    def installScripts(self):
        exSc = self.webScripts.findScript('ipfs-http-client')
        if exSc.isNull():
            scripts = self.app.scriptsIpfs
            [self.webScripts.insert(script) for script in scripts]

        if self.app.settingsMgr.ethereumEnabled:
            ethereumScripts = ethereumClientScripts(
                self.app.getEthParams())
            if ethereumScripts:
                [self.webScripts.insert(script) for script in
                 ethereumScripts]


class OrbitPage(BasePage):
    def installScripts(self):
        exSc = self.webScripts.findScript('ipfs-http-client')
        if exSc.isNull():
            log.debug('Adding ipfs-http-client scripts')

            scripts = ipfsClientScripts(self.app.getIpfsConnectionParams())
            for script in scripts:
                self.webScripts.insert(script)

        exSc = self.webScripts.findScript('orbit-db')
        if exSc.isNull():
            log.debug('Adding orbit-db scripts')
            scripts = orbitScripts(self.app.getIpfsConnectionParams())
            for script in scripts:
                self.webScripts.insert(script)


class HashmarksHandler(BaseHandler):
    marksListed = pyqtSignal(str, QJsonValue)

    def __init__(self, marksLocal, marksShared, parent=None):
        super(HashmarksHandler, self).__init__(parent)
        self.marksLocal = marksLocal
        self.marksShared = marksShared

    @pyqtSlot(str, result=list)
    def categories(self, ns):
        if ns == 'local':
            return self.marksLocal.getCategories()
        else:
            return self.marksShared.getCategories()

    @pyqtSlot(str, str, result=QJsonValue)
    def marks(self, cat, ns):
        source = self.marksLocal if ns == 'local' else self.marksShared
        marks = source.getCategoryMarks(cat)
        return QJsonValue.fromVariant(QVariant(marks))

    @pyqtSlot(str, result=bool)
    def deleteHashmark(self, path):
        return self.marksLocal.delete(path)


class HashmarksPage(IPFSPage):
    def __init__(self, marksLocal, marksNetwork, parent=None):
        super(HashmarksPage, self).__init__('hashmarks.html', parent=parent)

        self.marksLocal = marksLocal
        self.marksNetwork = marksNetwork
        self.marksLocal.markAdded.connect(
            lambda path, mark: self.onMarksChanged())
        self.marksLocal.markDeleted.connect(
            lambda path: self.onMarksChanged())
        self.marksLocal.feedMarkAdded.connect(
            lambda path, mark: self.onMarksChanged())

        self.hashmarks = HashmarksHandler(self.marksLocal,
                                          self.marksNetwork, self)
        self.register('hashmarks', self.hashmarks)
        self.register('galacteek', GalacteekHandler(None))

        self.timerRerender = QTimer()

    def onMarksChanged(self):
        ensure(self.render())

    def onSharedMarksChanged(self):
        if self.timerRerender.isActive():
            self.timerRerender.stop()
        self.timerRerender.start(2000)

    async def render(self):
        self.setHtml(await renderTemplate(
            self.template,
            ipfsConnParams=self.app.getIpfsConnectionParams(),
            marks=self.marksLocal,
            marksShared=self.marksNetwork),
            baseUrl=QUrl('qrc:/'))


class PDFViewerHandler(BaseHandler):
    marksListed = pyqtSignal(str, QJsonValue)

    def __init__(self, ipfsPath, parent=None):
        super(PDFViewerHandler, self).__init__(parent)
        self.ipfsPath = ipfsPath

    @pyqtSlot(result=str)
    def getPdfPath(self):
        return self.ipfsPath


class PDFViewerPage(IPFSPage):
    def __init__(self, ipfsPath, parent=None):
        super(PDFViewerPage, self).__init__('pdfviewer.html', parent=parent)
        self.ipfsPath = ipfsPath
        self.register('galacteek', GalacteekHandler(None))
        self.register('pdfview', PDFViewerHandler(self.ipfsPath))


class DWebView(QWebEngineView):
    def __init__(self, page=None, parent=None):
        super(DWebView, self).__init__(parent)
        self.channel = QWebChannel()
        self.p = page
        self.show()

    @property
    def p(self):
        return self._currentPage

    @p.setter
    def p(self, page):
        if page:
            self._currentPage = page
            self.setPage(page)


class WebTab(GalacteekTab):
    def __init__(self, mainW):
        super(WebTab, self).__init__(mainW)

    def attach(self, view):
        self.vLayout.addWidget(view)
