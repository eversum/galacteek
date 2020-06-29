import asyncio
import async_timeout

from PyQt5.QtWebEngineWidgets import QWebEnginePage
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtCore import pyqtSignal
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

from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import stripIpfs
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import cidConvertBase32
from galacteek.ipfs.ipfsops import *
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.search import multiSearch
from galacteek.ipfs.stat import StatInfo
from galacteek.dweb.render import renderTemplate
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
        self.setHtml(html)


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
        self.webProfile = self.app.webProfiles['ipfs']

    def getPage(self):
        return SearchResultsPage(
            self.webProfile,
            self.resultsTemplate,
            self.app.getIpfsConnectionParams(),
            parent=self
        )


class SearchResultsPage(BaseSearchPage):
    def __init__(
            self,
            profile,
            tmplMain,
            ipfsConnParams,
            webchannel=None,
            parent=None):
        super(SearchResultsPage, self).__init__(parent, profile=profile)

        self.channel = QWebChannel(self)
        self.handler = IPFSSearchHandler(self)
        self.channel.registerObject('ipfssearch', self.handler)
        self.setWebChannel(self.channel)

        self.app = QApplication.instance()

        self.template = tmplMain
        self.ipfsConnParams = ipfsConnParams
        ensure(self.render())

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        log.debug(
            'JS: level: {0}, source: {1}, line: {2}, message: {3}'.format(
                level,
                sourceId,
                lineNumber,
                message))

    async def render(self):
        html = await renderTemplate(self.template,
                                    ipfsConnParams=self.ipfsConnParams)
        self.setHtml(html)


class IPFSSearchHandler(QObject):
    resultReady = pyqtSignal(str, str, QVariant)
    objectStatAvailable = pyqtSignal(str, dict)

    filtersChanged = pyqtSignal()
    clear = pyqtSignal()
    resetForm = pyqtSignal()
    vPageStatus = pyqtSignal(int, int)

    searchTimeout = pyqtSignal(int)
    searchError = pyqtSignal()
    searchStarted = pyqtSignal(str)
    searchComplete = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)

        self.app = QApplication.instance()

        self.vPageCurrent = 0
        self.pagesPerVpage = 1
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

    def setSearchWidget(self, widget):
        self.searchW = widget

    def reload(self):
        self.vPageCurrent = 0
        self.filtersChanged.emit()

    def formReset(self):
        self.resetForm.emit()

    def cleanup(self):
        self._cancelTasks()

        self.vPageCurrent = 0
        self.clear.emit()
        self._cResults = []

    def _cancelTasks(self):
        try:
            if self._taskSearch:
                self._taskSearch.cancel()

            for task in self._tasks:
                task.cancel()
                self._tasks.remove(task)
        except Exception:
            log.debug('Failed to cancel search tasks')

        self._tasks = []

    def spawnSearchTask(self):
        self._taskSearch = ensure(self.runSearch(self.searchQuery))

    @pyqtSlot()
    def cancelSearchTasks(self):
        self._cancelTasks()

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
            self.spawnSearchTask()

    @pyqtSlot()
    def nextPage(self):
        self._cancelTasks()
        self.clear.emit()
        self.vPageCurrent += 1
        self.spawnSearchTask()

    @pyqtSlot(str)
    def openLink(self, path):
        ensure(self.app.resourceOpener.open(path, openingFrom='ipfssearch'))

    @pyqtSlot(str)
    def clipboardInput(self, path):
        if isinstance(path, str):
            self.app.setClipboardText(path)

    def findByHash(self, mHash):
        for result in self._cResults:
            hit = result['hit']
            hitHash = hit.get('hash')

            if not hitHash:
                continue

            if cidConvertBase32(hitHash) == cidConvertBase32(mHash):
                return hit

    @pyqtSlot(str)
    def hashmark(self, path):
        hashV = stripIpfs(path)
        hit = self.findByHash(hashV)

        title = hit.get('title', iUnknown()) if hit else hashV
        descr = hit.get('description', iUnknown()) if hit else ''
        type = hit.get('type') if hit else None
        pinSingle = (type == 'file')
        pinRecursive = (type == 'directory')

        ensure(addHashmarkAsync(
            path, title=title, description=descr,
            pin=pinSingle, pinRecursive=pinRecursive))

    @pyqtSlot(str)
    def mplayerQueue(self, path):
        self.app.mainWindow.mediaPlayerQueue(path, playLast=True)

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

        self.spawnSearchTask()

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
        elif cType == 'web':
            filters['metadata.Content-Type'] = 'text/html'

        return filters

    def sendHit(self, hit):
        hitHash = hit.get('hash', None)
        mimeType = hit.get('mimetype', None)

        ipfsPath = IPFSPath(hitHash, autoCidConv=True)
        if not ipfsPath.valid:
            return

        sizeFormatted = sizeFormat(hit.get('size', 0))

        pHit = {
            'hash': hitHash,
            'path': str(ipfsPath),
            'url': ipfsPath.ipfsUrl,
            'mimetype': mimeType if mimeType else '',
            'title': hit.get('title', iUnknown()),
            'size': hit.get('size', iUnknown()),
            'sizeformatted': sizeFormatted,
            'description': hit.get('description', None),
            'type': hit.get('type', iUnknown()),
            'first-seen': hit.get('first-seen', iUnknown())
        }

        self.resultReady.emit('ipfs-search', hitHash, QVariant(pHit))

    async def sendCyberHit(self, hit):
        hitHash = hit.get('hash')

        ipfsPath = IPFSPath(hitHash)
        if not ipfsPath.valid:
            return

        mType, stat = await self.app.rscAnalyzer(
            ipfsPath,
            fetchExtraMetadata=True
        )

        if not mType or not stat:
            return

        sInfo = StatInfo(stat)

        pHit = {
            'hash': hitHash,
            'path': str(ipfsPath),
            'cyberlink': hit['cyberlink'],
            'url': ipfsPath.ipfsUrl,
            'mimetype': str(mType),
            'title': hitHash,
            'size': sInfo.totalSize,
            'sizeformatted': sizeFormat(sInfo.totalSize),
            'description': None,
            'type': iUnknown(),
            'first-seen': iUnknown()
        }

        self.resultReady.emit('cyber', hitHash, QVariant(pHit))
        self.objectStatAvailable.emit(hitHash, stat)

    async def fetchObjectStat(self, ipfsop, cid):
        path = joinIpfs(cid)

        try:
            mType, stat = await self.app.rscAnalyzer(
                path, fetchExtraMetadata=True)
            if stat:
                self.objectStatAvailable.emit(cid, stat)
        except Exception:
            pass

    @ipfsOp
    async def runSearch(self, ipfsop, searchQuery, timeout=30):
        pageStart = self.vPageCurrent * self.pagesPerVpage
        statusEmitted = False
        gotResults = False

        try:
            with async_timeout.timeout(timeout):
                async for pageCount, result in multiSearch(
                        searchQuery,
                        page=pageStart,
                        filters=self.filters,
                        sslverify=self.app.sslverify):
                    await asyncio.sleep(0)
                    gotResults = True

                    if not statusEmitted:
                        self.vPageStatus.emit(
                            self.vPageCurrent + 1,
                            pageCount if pageCount > 0 else 1)
                        statusEmitted = True

                    hit = result['hit']
                    engine = result['engine']

                    self._cResults.append(result)

                    if engine == 'ipfs-search':
                        self.sendHit(hit)
                        self._tasks.append(ensure(
                            self.fetchObjectStat(
                                ipfsop, hit['hash'])))
                    else:
                        self._tasks.append(
                            ensure(self.sendCyberHit(hit)))
        except asyncio.TimeoutError:
            self.searchTimeout.emit(timeout)
            return False
        except asyncio.CancelledError:
            return False
        except Exception as e:
            log.debug(
                'IPFSSearch: unknown exception while searching: {}'.format(
                    str(e)))
            return False

        if gotResults:
            self.searchComplete.emit()
            return True
        else:
            self.searchError.emit()
            return False


class IPFSSearchView(QWidget):
    titleNeedUpdate = pyqtSignal(str)

    def __init__(self, searchQuery='', parent=None):
        super(IPFSSearchView, self).__init__(parent)
        self.setLayout(QVBoxLayout())

        self.tab = parent

        self.app = QApplication.instance()
        self.setAttribute(Qt.WA_DeleteOnClose)

        # Templates
        self.resultsTemplate = self.app.getJinjaTemplate('ipfssearch.html')
        self.loadingTemplate = self.app.getJinjaTemplate(
            'ipfssearch-loading.html')

        self.browser = QWebEngineView(parent=self)
        self.layout().addWidget(self.browser)

        self.resultsPage = self.app.mainWindow.ipfsSearchPageFactory.getPage()
        self.resultsPage.setParent(self)

        self.resultsPage.handler.searchStarted.connect(
            lambda query: self.titleNeedUpdate.emit(query))

        self.browser.setPage(self.resultsPage)
        self.browser.setFocus(Qt.OtherFocusReason)


class IPFSSearchTab(GalacteekTab):
    def __init__(self, gWindow, query=None):
        super(IPFSSearchTab, self).__init__(gWindow)

        self.view = IPFSSearchView(query, parent=self)
        self.view.titleNeedUpdate.connect(
            lambda text: self.setTabName(iIpfsSearchText(text[0:12])))
        self.addToLayout(self.view)
