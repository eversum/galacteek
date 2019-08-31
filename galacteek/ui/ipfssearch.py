import asyncio
import async_timeout
import uuid

from PyQt5.QtWebEngineWidgets import QWebEnginePage
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEngineProfile
from PyQt5.QtWebChannel import QWebChannel

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QRegularExpression

from PyQt5.QtCore import QVariant

from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QVBoxLayout

from PyQt5.QtGui import QSyntaxHighlighter
from PyQt5.QtGui import QTextCharFormat
from PyQt5.QtGui import QFont

from galacteek.ipfs.cidhelpers import cidValid
from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import stripIpfs
from galacteek.ipfs.ipfsops import *
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs import ipfssearch
from galacteek.dweb.render import renderTemplate
from galacteek.core.analyzer import ResourceAnalyzer
from galacteek import ensure
from galacteek import log

from .helpers import *
from .hashmarks import *
from .widgets import *
from .i18n import *


def iResultsInfo(count, maxScore):
    return QCoreApplication.translate(
        'IPFSSearchResults',
        'Results count: <b>{0}</b> (max score: <b>{1}</b>)').format(
        count,
        maxScore)


def iNoResults():
    return QCoreApplication.translate('IPFSSearchResults',
                                      '<b>No results found</b>')


def iErrFetching():
    return QCoreApplication.translate('IPFSSearchResults',
                                      '<b>Error while fetching results</b>')


def iSearching():
    return QCoreApplication.translate('IPFSSearchResults',
                                      '<b>Searching ...</b>')


class IPFSSearchButton(QToolButton):
    hovered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.iconNormal = getIcon('search-engine.png')
        self.iconActive = getIcon('search-engine-zoom.png')

    def enterEvent(self, ev):
        self.hovered.emit()


class Highlighter(QSyntaxHighlighter):
    """
    Highlights the search query string in the results
    """

    def __init__(self, highStr, doc):
        super().__init__(doc)

        self.highStr = highStr
        self.fmt = QTextCharFormat()
        self.fmt.setFontWeight(QFont.Bold)
        self.fmt.setForeground(Qt.red)

    def highlightBlock(self, text):
        rExpr = QRegularExpression(self.highStr)
        matches = rExpr.globalMatch(text)

        if not matches.isValid():
            return

        while matches.hasNext():
            match = matches.next()
            if not match.isValid():
                break
            self.setFormat(match.capturedStart(), match.capturedLength(),
                           self.fmt)


class NoResultsPage(QWebEnginePage):
    def __init__(self, tmpl, parent=None):
        super(NoResultsPage, self).__init__(parent)
        self.setHtml('<html><body><p>NO RESULTS</p></body></html>')


class BaseSearchPage(QWebEnginePage):
    pageRendered = pyqtSignal(str)

    def __init__(self, parent, profile=None):
        if profile:
            super(BaseSearchPage, self).__init__(profile, parent)
        else:
            super(BaseSearchPage, self).__init__(parent)

        self.pageRendered.connect(self.onPageRendered)

    def onPageRendered(self, html):
        self.setHtml(html, baseUrl=QUrl('qrc:/'))


class SearchInProgressPage(BaseSearchPage):
    def __init__(self, tmpl, parent=None):
        super(SearchInProgressPage, self).__init__(parent)
        self.template = tmpl
        ensure(self.render())

    async def render(self):
        html = await renderTemplate(self.template)
        if html:
            self.pageRendered.emit(html)


class SearchResultsPageFactory(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = QApplication.instance()
        self.resultsTemplate = self.app.getJinjaTemplate('ipfssearch.html')

        self.webProfile = QWebEngineProfile()
        self.installScripts()

        self._pages = {}
        self.genPages(3)

    def installScripts(self):
        self.webScripts = self.webProfile.scripts()

        exSc = self.webScripts.findScript('ipfs-http-client')
        if self.app.settingsMgr.jsIpfsApi is True and exSc.isNull():
            for script in self.app.scriptsIpfs:
                self.webScripts.insert(script)

    def genPages(self, count):
        [self.makePage() for i in range(0, count)]

    def getPage(self):
        for uid, data in self._pages.items():
            page = data['page']
            if not page.used:
                page.used = True
                self.app.loop.call_soon(self.genPages, 2)
                return page, data['handler'], data['channel']

    def makePage(self):
        uid = str(uuid.uuid4())
        handler = IPFSSearchHandler(self)
        channel = QWebChannel()

        self._pages[uid] = {
            'channel': channel,
            'page': None,
            'handler': handler
        }

        channel.registerObject('ipfssearch', handler)

        resultsPage = SearchResultsPage(
            self.webProfile,
            handler,
            self.resultsTemplate,
            None,
            self.app.getIpfsConnectionParams(),
            parent=self,
            webchannel=self._pages[uid]['channel']
        )

        self._pages[uid]['page'] = resultsPage
        return resultsPage


class SearchResultsPage(BaseSearchPage):
    def __init__(
            self,
            profile,
            handler,
            tmplMain,
            tmplHits,
            ipfsConnParams,
            webchannel=None,
            parent=None):
        super(SearchResultsPage, self).__init__(parent, profile=profile)

        self.used = False

        if webchannel:
            self.setWebChannel(webchannel)

        self.app = QApplication.instance()

        self.url = QUrl('qrc:/')
        self.handler = handler
        self.template = tmplMain
        self.templateHits = tmplHits
        self.ipfsConnParams = ipfsConnParams
        self.noStatTimeout = 12
        ensure(self.render())

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        log.info(
            'JS: level: {0}, source: {1}, line: {2}, message: {3}'.format(
                level,
                sourceId,
                lineNumber,
                message))

    async def render(self):
        html = await renderTemplate(self.template,
                                    ipfsConnParams=self.ipfsConnParams)
        self.setHtml(html, baseUrl=QUrl('qrc:/'))


class IPFSSearchHandler(QObject):
    ready = pyqtSignal()

    resultsReceived = pyqtSignal(ipfssearch.IPFSSearchResults, bool)

    resultReady = pyqtSignal(str, QVariant)

    objectReady = pyqtSignal(str)
    objectStatAvailable = pyqtSignal(str, dict, dict)
    objectStatUnavailable = pyqtSignal(str)

    filtersChanged = pyqtSignal()
    clear = pyqtSignal()
    resetForm = pyqtSignal()
    vPageChanged = pyqtSignal(int)
    vPageStatus = pyqtSignal(int, int)
    searchTimeout = pyqtSignal(int)
    searchError = pyqtSignal()
    searchStarted = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.analyzer = ResourceAnalyzer(self)
        self.noStatTimeout = 8

        self.vPageCurrent = 0
        self.pagesPerVpage = 2
        self.pageCount = 0
        self.searchQuery = ''

        self.filters = {}
        self._tasks = []
        self._taskSearch = None
        self._cResults = []

    @property
    def vPageCurrent(self):
        return self._vPageCurrent

    @vPageCurrent.setter
    def vPageCurrent(self, page):
        self._vPageCurrent = page
        self.vPageChanged.emit(self.vPageCurrent)

    def setSearchWidget(self, widget):
        self.searchW = widget

    def reload(self):
        self.vPageCurrent = 0
        self.filtersChanged.emit()

    def init(self):
        self.vPageCurrent = 0

    def formReset(self):
        self.resetForm.emit()

    def cleanup(self):
        self._cancelTasks()
        if self._taskSearch:
            self._taskSearch.cancel()
        self.clear.emit()
        self._cResults = []

    def _cancelTasks(self):
        for task in self._tasks:
            task.cancel()

        self._tasks = []

    @pyqtSlot(str)
    def fetchObject(self, path):
        ensure(self.fetch(path))

    @pyqtSlot(str)
    def pinObject(self, path):
        ensure(self.pin(path))

    @ipfsOp
    async def pin(self, op, path):
        pinner = op.ctx.pinner
        await pinner.queue(path, True, None, qname='ipfs-search')

    @pyqtSlot()
    def previousPage(self):
        if self.vPageCurrent > 0:
            self._cancelTasks()
            self.clear.emit()
            self.vPageCurrent -= 1
            ensure(self.runSearch(self.searchQuery))

    @pyqtSlot()
    def nextPage(self):
        self._cancelTasks()
        self.clear.emit()
        self.vPageCurrent += 1
        ensure(self.runSearch(self.searchQuery))

    @ipfsOp
    async def fetch(self, op, path):
        import tempfile
        try:
            data = await asyncio.wait_for(
                op.client.cat(path), 5)
        except BaseException:
            pass
        else:
            file = tempfile.NamedTemporaryFile(delete=False)
            file.write(data)
            self.objectReady.emit(file.name)

    @pyqtSlot(str)
    def openLink(self, path):
        ensure(self.app.resourceOpener.open(path))

    @pyqtSlot(str)
    def clipboardInput(self, path):
        if isinstance(path, str):
            self.app.setClipboardText(path)

    def findByHash(self, mHash):
        for results in self._cResults:
            found = results.findByHash(mHash)
            if found:
                return found

    @pyqtSlot(str)
    def hashmark(self, path):
        hashV = stripIpfs(path)
        hit = self.findByHash(hashV)

        if not hit:
            return

        title = hit.get('title', iUnknown()) if hit else ''
        descr = hit.get('description', iUnknown()) if hit else ''
        type = hit.get('type', None)
        pinSingle = (type == 'file')
        pinRecursive = (type == 'directory')

        addHashmark(self.app.marksLocal,
                    path, title, description=descr,
                    pin=pinSingle, pinRecursive=pinRecursive)

    @pyqtSlot(str)
    def explore(self, path):
        hashV = stripIpfs(path)
        if hashV:
            self.app.mainWindow.explore(hashV)

    @pyqtSlot(str, str)
    def search(self, searchQuery, cType):
        self.cleanup()
        self.searchQuery = searchQuery
        self.searchStarted.emit(self.searchQuery)
        self.filters = self.getFilters(cType)
        self._taskSearch = ensure(self.runSearch(searchQuery))

    def getFilters(self, cTypeS):
        filters = {}

        cType = cTypeS.lower()

        if cType == 'images':
            filters['metadata.Content-Type'] = 'image*'
        elif cType == 'videos':
            filters['metadata.Content-Type'] = 'video*'
        elif cType == 'music':
            filters['metadata.Content-Type'] = 'audio*'
        elif cType == 'text':
            filters['metadata.Content-Type'] = 'text*'

        return filters

    def sendHit(self, hit):
        hitHash = hit.get('hash', None)
        mimeType = hit.get('mimetype', None)

        if hitHash is None or not cidValid(hitHash):
            return

        path = joinIpfs(hitHash)
        sizeFormatted = sizeFormat(hit.get('size', 0))

        pHit = {
            'hash': hitHash,
            'path': path,
            'mimetype': mimeType if mimeType else '',
            'title': hit.get('title', iUnknown()),
            'size': hit.get('size', iUnknown()),
            'sizeformatted': sizeFormatted,
            'description': hit.get('description', None),
            'type': hit.get('type', iUnknown()),
            'first-seen': hit.get('first-seen', iUnknown())
        }

        self.resultReady.emit(hitHash, QVariant(pHit))

    async def fetchObjectStat(self, ipfsop, hit):
        cid = hit['hash']
        path = joinIpfs(cid)

        stat = await ipfsop.objStatCtxUpdate(path, timeout=self.noStatTimeout)
        if stat:
            self.objectStatAvailable.emit(cid, stat, hit)

    @ipfsOp
    async def runSearch(self, ipfsop, searchQuery, timeout=20):
        pageStart = self.vPageCurrent * self.pagesPerVpage
        pageCount = 0
        gotResults = False
        statusEmitted = False

        try:
            with async_timeout.timeout(timeout):
                async for sr in ipfssearch.search(
                        searchQuery,
                        pageStart=pageStart,
                        preloadPages=self.pagesPerVpage,
                        filters=self.filters,
                        sslverify=self.app.sslverify):
                    gotResults = True

                    await asyncio.sleep(0)
                    pageCount = sr.pageCount

                    if not isinstance(pageCount, int) or pageCount <= 0:
                        break

                    vpCount = pageCount / self.pagesPerVpage

                    if not statusEmitted:
                        self.vPageStatus.emit(self.vPageCurrent + 1,
                                              vpCount if vpCount > 0 else 1)
                        statusEmitted = True

                    self._cResults.append(sr)
                    self.pageCount = pageCount

                    for hit in sr.hits:
                        self.sendHit(hit)

                        await asyncio.sleep(0.2)

                        self._tasks.append(
                            ensure(self.fetchObjectStat(ipfsop, hit)))
        except asyncio.TimeoutError:
            self.searchTimeout.emit(timeout)
        except asyncio.CancelledError:
            self.searchTimeout.emit(timeout)
        except Exception:
            pass

        if not gotResults:
            self.searchError.emit()


class IPFSSearchView(QWidget):
    resultsReceived = pyqtSignal(ipfssearch.IPFSSearchResults, bool)
    titleNeedUpdate = pyqtSignal(str)

    def __init__(self, searchQuery='', parent=None):
        super(IPFSSearchView, self).__init__(parent)
        self.setLayout(QVBoxLayout())

        self.tab = parent

        self.app = QApplication.instance()
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Templates
        self.resultsTemplate = self.app.getJinjaTemplate('ipfssearch.html')
        self.hitsTemplate = self.app.getJinjaTemplate('ipfssearch-hits.html')
        self.loadingTemplate = self.app.getJinjaTemplate(
            'ipfssearch-loading.html')

        self.browser = QWebEngineView(parent=self)
        self.layout().addWidget(self.browser)

        self.resultsPage, self.handler, self.channel = \
            self.app.mainWindow.ipfsSearchPageFactory.getPage()
        self.resultsPage.setParent(self)

        self.handler.searchStarted.connect(
            lambda query: self.titleNeedUpdate.emit(query))

        self.browser.setPage(self.resultsPage)
        self.browser.setFocus(Qt.OtherFocusReason)

        self.handler.init()


class IPFSSearchTab(GalacteekTab):
    def __init__(self, gWindow, query=None):
        super(IPFSSearchTab, self).__init__(gWindow)

        self.view = IPFSSearchView(query, parent=self)
        self.view.titleNeedUpdate.connect(
            lambda text: self.setTabName(iIpfsSearchText(text[0:12])))
        self.addToLayout(self.view)

    def onClose(self):
        self.view.handler.cleanup()
        self.view.handler.formReset()
        self.view.resultsPage.used = False
        del self.view
        return True
