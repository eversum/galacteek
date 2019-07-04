import asyncio
import time

from PyQt5.QtWebEngineWidgets import QWebEnginePage
from PyQt5.QtWebChannel import QWebChannel

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QRegularExpression

from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QStackedWidget
from PyQt5.QtWidgets import QStyle
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QToolButton

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
from galacteek import ensure
from galacteek import log

from . import ui_ipfssearchinput
from . import ui_ipfssearchw
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
        self.setCheckable(True)
        self.setAutoRaise(True)

    def enterEvent(self, ev):
        self.hovered.emit()


class IPFSSearchWidget(QWidget):
    runSearch = pyqtSignal(str)
    hidden = pyqtSignal()

    def __init__(self, parent=None):
        super(IPFSSearchWidget, self).__init__(
            parent, Qt.Widget | Qt.FramelessWindowHint)

        self.input = ui_ipfssearchinput.Ui_SearchInput()
        self.input.setupUi(self)
        self.input.searchQuery.returnPressed.connect(self.onSearch)

    def focus(self):
        self.input.searchQuery.setFocus(Qt.OtherFocusReason)

    def onSearch(self):
        text = self.input.searchQuery.text()
        self.input.searchQuery.clear()
        self.runSearch.emit(text)
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()

    def hideEvent(self, event):
        self.hidden.emit()


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

    def __init__(self, parent):
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


class SearchResultsPage(BaseSearchPage):
    def __init__(
            self,
            handler,
            tmplMain,
            tmplHits,
            ipfsConnParams,
            webchannel=None,
            parent=None):
        super(SearchResultsPage, self).__init__(parent)

        if webchannel:
            self.setWebChannel(webchannel)

        self.app = QApplication.instance()
        self.handler = handler
        self.template = tmplMain
        self.templateHits = tmplHits
        self.ipfsConnParams = ipfsConnParams
        self.noStatTimeout = 12
        self.installScripts()
        ensure(self.render())

    def installScripts(self):
        self.webScripts = self.profile().scripts()

        exSc = self.webScripts.findScript('ipfs-http-client')
        if self.app.settingsMgr.jsIpfsApi is True and exSc.isNull():
            for script in self.app.scriptsIpfs:
                self.webScripts.insert(script)

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceId):
        log.info(
            'JS: level: {0}, source: {1}, line: {2}, message: {3}'.format(
                level,
                sourceId,
                lineNumber,
                message))

    async def render(self):
        html = await renderTemplate(self.template)
        if html:
            self.pageRendered.emit(html)

    async def renderHits(self, pageNo, pageCount, results):
        """
        This used to be a simple function and not a coroutine
        but now that we use jinja in async mode ..

        Ensuring the fetchObjectStat task could be a source of
        problems here, this should be changed
        """
        ctxHits = []

        for hit in results.hits:
            hitHash = hit.get('hash', None)
            mimeType = hit.get('mimetype', None)

            if hitHash is None or not cidValid(hitHash):
                continue

            path = joinIpfs(hitHash)
            sizeFormatted = sizeFormat(hit.get('size', 0))

            ctxHits.append({
                'hash': hitHash,
                'path': path,
                'mimetype': mimeType if mimeType else '',
                'title': hit.get('title', iUnknown()),
                'size': hit.get('size', iUnknown()),
                'sizeformatted': sizeFormatted,
                'description': hit.get('description', None),
                'type': hit.get('type', iUnknown()),
                'first-seen': hit.get('first-seen', iUnknown())
            })

            ensure(self.fetchObjectStat(hitHash, path))

        return await self.templateHits.render_async(
            hits=ctxHits,
            resultsCount=results.resultsCount,
            pageCount=results.pageCount,
            showPrevious=pageNo > 1,
            showNext=pageNo < pageCount,
            ipfsConnParams=self.ipfsConnParams
        )

    @ipfsOp
    async def fetchObjectStat(self, op, cid, path):
        def statCallback(f):
            try:
                result = f.result()
            except BaseException as err:
                log.debug('Exception on stat', exc_info=err)
                return
            if isinstance(result, dict):
                self.handler.objectStatAvailable.emit(cid, result)
            else:
                self.handler.objectStatUnavailable.emit(cid)

        if path not in op.ctx.objectStats:
            f = ensure(op.objStatCtxUpdate(path, timeout=self.noStatTimeout))
            f.add_done_callback(statCallback)
        else:
            stat = op.ctx.objectStats.get(path)
            if stat is None:
                self.handler.objectStatUnavailable.emit(cid)


class IPFSSearchHandler(QObject):
    ready = pyqtSignal()

    resultsReceived = pyqtSignal(ipfssearch.IPFSSearchResults, bool)
    resultsReadyDom = pyqtSignal(str)

    objectReady = pyqtSignal(str)
    objectStatAvailable = pyqtSignal(str, dict)
    objectStatUnavailable = pyqtSignal(str)

    filtersChanged = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.searchW = parent
        self.currentResults = None
        self.uiCtrl = self.searchW.ui
        self.resultsReceived.connect(self.onResultsRx)
        self.app = QApplication.instance()
        self._reset()

    def reload(self):
        self.filtersChanged.emit()

    def _reset(self):
        self.pages = {}
        self.pageCount = 0

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
        self.searchW.onPrevPage()

    @pyqtSlot()
    def nextPage(self):
        self.searchW.onNextPage()

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

    @pyqtSlot(str)
    def hashmark(self, path):
        hashV = stripIpfs(path)

        if not self.currentResults:
            return

        hit = self.currentResults.findByHash(hashV)

        if not hit:
            return

        title = hit.get('title', iUnknown()) if hit else ''
        descr = hit.get('description', iUnknown()) if hit else ''
        type = hit.get('type', None)
        pinSingle = (type == 'file')
        pinRecursive = (type == 'directory')

        addHashmark(self.searchW.app.marksLocal,
                    path, title, description=descr,
                    pin=pinSingle, pinRecursive=pinRecursive)

    @pyqtSlot(str)
    def explore(self, path):
        hashV = stripIpfs(path)
        if hashV:
            self.searchW.app.mainWindow.explore(hashV)

    @pyqtSlot()
    def search(self):
        ensure(self.runSearch(self.uiCtrl.searchQuery.text()))

    async def runSearch(self, searchQuery):
        self.searchW.loading()

        async for sr in ipfssearch.search(searchQuery, preloadPages=0,
                                          filters=self.searchW.getFilters(),
                                          sslverify=self.app.sslverify):
            await asyncio.sleep(0)
            pageCount = sr.pageCount

            if pageCount == 0:
                self.searchW.noResults()
                break

            if sr.page == 0 and self.uiCtrl.comboPages.count() == 0:
                resCount = sr.results.get('total', iUnknown())
                maxScore = sr.results.get('max_score', iUnknown())
                self.uiCtrl.labelInfo.setText(iResultsInfo(resCount, maxScore))

                if pageCount > 256:
                    pageCount = 256

                self.pageCount = pageCount

                for pageNum in range(1, pageCount + 1):
                    self.uiCtrl.comboPages.insertItem(
                        pageNum, 'Page {}'.format(pageNum))

            self.resultsReceived.emit(sr, False)

    async def runSearchPage(self, searchQuery, page, display=False):
        sr = await ipfssearch.getPageResults(searchQuery, page,
                                             filters=self.searchW.getFilters(),
                                             sslverify=self.app.sslverify)
        if sr:
            self.resultsReceived.emit(sr, display)

    def onResultsRx(self, sr, display):
        self.pages[sr.page] = {
            'results': sr,
            'time': int(time.time()),
            'page': self.searchW.resultsPage
        }

        self.currentResults = sr
        self.searchW.loadPage(sr.page)
        self.searchW.enableCombo()

    def getPageData(self, page):
        return self.pages.get(page, None)

    def getPageWidget(self, page):
        pageData = self.getPageData(page)
        if pageData:
            return pageData.get('page', None)


class IPFSSearchView(GalacteekTab):
    resultsReceived = pyqtSignal(ipfssearch.IPFSSearchResults, bool)

    def __init__(self, searchQuery, *args, **kw):
        super(IPFSSearchView, self).__init__(*args, **kw)

        self.searchWidget = QWidget()
        self.addToLayout(self.searchWidget)

        self.setAttribute(Qt.WA_DeleteOnClose)

        # Templates
        self.resultsTemplate = self.app.getJinjaTemplate('ipfssearch.html')
        self.hitsTemplate = self.app.getJinjaTemplate('ipfssearch-hits.html')
        self.loadingTemplate = self.app.getJinjaTemplate(
            'ipfssearch-loading.html')

        self.searchQuery = searchQuery

        self.ui = ui_ipfssearchw.Ui_IPFSSearchMain()
        self.ui.setupUi(self.searchWidget)
        self.ui.searchQuery.setText(self.searchQuery)

        self.stack = QStackedWidget()
        self.channel = QWebChannel()
        self.handler = IPFSSearchHandler(self)
        self.channel.registerObject('ipfssearch', self.handler)

        self.loadingPage = SearchInProgressPage(
            self.loadingTemplate,
            parent=self
        )

        self.resultsPage = SearchResultsPage(
            self.handler,
            self.resultsTemplate,
            self.hitsTemplate,
            self.app.getIpfsConnectionParams(),
            parent=self,
            webchannel=self.channel
        )

        self.ui.comboPages.activated.connect(self.onComboPages)
        self.ui.prevPageButton.clicked.connect(self.onPrevPage)
        self.ui.nextPageButton.clicked.connect(self.onNextPage)
        self.ui.prevPageButton.setIcon(
            self.style().standardIcon(QStyle.SP_MediaSkipBackward))
        self.ui.nextPageButton.setIcon(
            self.style().standardIcon(QStyle.SP_MediaSkipForward))

        self.ui.itemTypeFilter.addItem('All')
        self.ui.itemTypeFilter.addItem('Files')
        self.ui.itemTypeFilter.addItem('Directories')

        self.ui.contentTypeFilter.addItem('All')
        self.ui.contentTypeFilter.addItem('Images')
        self.ui.contentTypeFilter.addItem('Videos')
        self.ui.contentTypeFilter.addItem('Text')
        self.ui.contentTypeFilter.addItem('Music')

        for i in range(20, 200, 10):
            self.ui.resultsPerPage.addItem(str(i))

        self.ui.resultsPerPage.setCurrentIndex(0)

        self.lastSeenDays = 365

        self.ui.lastSeenSlider.setTickInterval(1)
        self.ui.lastSeenSlider.setMinimum(1)
        self.ui.lastSeenSlider.setMaximum(365 * 7)
        self.ui.lastSeenSlider.valueChanged.connect(self.onSliderChanged)
        self.ui.lastSeenSlider.setValue(self.lastSeenDays)
        self.ui.lastSeenSlider.sliderReleased.connect(self.onFiltersChanged)
        self.setResultsPage()

        # Rerender when the filters change
        self.ui.filenameFilter.returnPressed.connect(self.onFiltersChanged)
        self.ui.searchQuery.returnPressed.connect(self.onFiltersChanged)
        self.ui.searchQuery.returnPressed.connect(self.onFiltersChanged)
        self.ui.itemTypeFilter.currentTextChanged.connect(
            self.onFiltersChanged)
        self.ui.contentTypeFilter.currentTextChanged.connect(
            self.onFiltersChanged)
        self.ui.titleFilter.returnPressed.connect(self.onFiltersChanged)

    @property
    def currentPage(self):
        return self.ui.comboPages.currentIndex()

    @property
    def resultsPerPage(self):
        return int(self.ui.resultsPerPage.currentText())

    def setResultsPage(self):
        self.ui.browser.setPage(self.resultsPage)

    def setLoadingPage(self):
        self.ui.browser.setPage(self.loadingPage)

    def onSliderChanged(self, value):
        self.ui.lastSeenLabel.setText('{0} days'.format(str(value)))

    def onFiltersChanged(self):
        self.handler._reset()
        self.ui.comboPages.setCurrentIndex(0)
        self.lastSeenDays = self.ui.lastSeenSlider.value()
        self.searchQuery = self.ui.searchQuery.text()
        self.handler.reload()

    def loading(self):
        self.setLoadingPage()
        self.ui.labelInfo.setText(iSearching())
        self.ui.comboPages.clear()

    def noResults(self):
        self.addEmptyResultsPage()
        self.enableNavArrows(False)
        self.disableCombo()

    def disableCombo(self):
        self.ui.comboPages.setEnabled(False)

    def enableCombo(self):
        self.ui.comboPages.setEnabled(True)

    def enableNavArrows(self, enable=True):
        self.ui.prevPageButton.setEnabled(enable)
        self.ui.nextPageButton.setEnabled(enable)

    def onPageChanged(self, idx):
        self.ui.prevPageButton.setEnabled(idx > 0)
        self.ui.nextPageButton.setEnabled(self.handler.pageCount > idx + 1)

    def onPrevPage(self):
        cIdx = self.currentPage
        self.loadPage(cIdx - 1)

    def onNextPage(self):
        cIdx = self.currentPage
        self.loadPage(cIdx + 1)

    def onComboPages(self, idx):
        self.loadPage(idx)

    def loadPage(self, pageNum):
        self.disableCombo()
        pageData = self.handler.getPageData(pageNum)

        if not pageData:
            ensure(self.handler.runSearchPage(self.searchQuery,
                                              pageNum, True))
        else:
            self.displayPage(pageNum)
            self.enableCombo()

    def addEmptyResultsPage(self):
        page = NoResultsPage(None, parent=self)
        self.ui.browser.setPage(page)
        self.ui.labelInfo.setText(iNoResults())

    def addErrorPage(self):
        pass

    def fileFilter(self):
        if self.ui.itemTypeFilter.currentIndex() == 1:
            objType = 'file'
        elif self.ui.itemTypeFilter.currentIndex() == 2:
            objType = 'directory'
        else:
            objType = 'all'
        return objType

    def getFilters(self):
        filters = {}

        filenameF = self.ui.filenameFilter.text()
        if len(filenameF) > 0:
            filters['references.name'] = filenameF

        titleF = self.ui.titleFilter.text()
        if len(titleF) > 0:
            filters['references.title'] = titleF

        if self.lastSeenDays in range(0, 31):
            filters['last-seen'] = '>now-{0}d'.format(self.lastSeenDays)
        elif self.lastSeenDays >= 31:
            filters['last-seen'] = '>now-{0}M'.format(
                int(self.lastSeenDays / 30))

        if self.fileFilter() == 'directory':
            filters['_type'] = 'directory'
        if self.fileFilter() == 'file':
            filters['_type'] = 'file'

        ctypeF = self.ui.contentTypeFilter.currentText()
        if ctypeF == 'Images':
            filters['metadata.Content-Type'] = 'image*'
        if ctypeF == 'Videos':
            filters['metadata.Content-Type'] = 'video*'
        if ctypeF == 'Music':
            filters['metadata.Content-Type'] = 'audio*'
        if ctypeF == 'Text':
            filters['metadata.Content-Type'] = 'text*'

        return filters

    def displayPage(self, page):
        self.setResultsPage()
        pageData = self.handler.getPageData(page)

        def hitsRendered(future, page):
            try:
                rendered = future.result()
            except Exception as err:
                log.debug('Exception rendering hits: {}'.format(
                    str(err)))
            else:
                self.ui.comboPages.setCurrentIndex(page)
                self.handler.resultsReadyDom.emit(rendered)
                self.onPageChanged(page)

        if pageData:
            ensure(self.resultsPage.renderHits(
                page, self.handler.pageCount, pageData['results']),
                futcallback=lambda future: hitsRendered(future, page))
