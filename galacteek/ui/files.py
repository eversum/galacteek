import os.path
import asyncio
import functools
import async_timeout
import time
import re
from datetime import datetime
from datetime import date
from pathlib import Path

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QActionGroup
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import QTreeView
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QAbstractItemView
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QFileSystemModel
from PyQt5.QtWidgets import QHeaderView

from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QDir
from PyQt5.QtCore import QSize
from PyQt5.QtCore import QDate
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QSortFilterProxyModel

from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QKeySequence

from galacteek import ensure
from galacteek import partialEnsure
from galacteek import GALACTEEK_NAME
from galacteek import AsyncSignal
from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import cidConvertBase32
from galacteek.ipfs.ipfsops import *
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.mimetype import MIMEType
from galacteek.appsettings import *

from galacteek.core import modelhelpers
from galacteek.core.models.mfs import MFSItem
from galacteek.core.models.mfs import MFSNameItem
from galacteek.core.models.mfs import MFSTimeFrameItem
from galacteek.core.models.mfs import MFSRootItem

from galacteek.did.ipid import IPService

from .dids import buildPublishingMenu
from . import ui_files
from . import ui_timeframeselector
from . import dag
from .i18n import *  # noqa
from .helpers import *  # noqa
from .widgets import GalacteekTab
from .widgets import AnimatedLabel
from .clips import RotatingCubeRedFlash140d
from .hashmarks import *  # noqa
from .clipboard import iCopyCIDToClipboard
from .clipboard import iCopyPathToClipboard
from .clipboard import iCopyPubGwUrlToClipboard
from .dialogs import MFSImportOptionsDialog

import aioipfs

# Files messages


def iFileImportError():
    return QCoreApplication.translate(
        'FileManagerForm', 'Error importing file {}')


def iFileImportCancelled():
    return QCoreApplication.translate(
        'FileManagerForm', 'Cancelled import')


def iAddedFile(name):
    return QCoreApplication.translate('FileManagerForm',
                                      'Added {0}').format(name)


def iImportHiddenFiles():
    return QCoreApplication.translate('FileManagerForm',
                                      'Import hidden files ?')


def iUseGitIgnoreRules():
    return QCoreApplication.translate('FileManagerForm',
                                      'Use .gitignore rules ?')


def iImportedCount(count):
    return QCoreApplication.translate('FileManagerForm',
                                      'Imported {0} file(s)').format(count)


def iLoadingFile(name):
    return QCoreApplication.translate('FileManagerForm',
                                      'Loading file {0}').format(name)


def iLoading(name):
    return QCoreApplication.translate('FileManagerForm',
                                      'Loading {0}').format(name)


def iListingMFSPath(path):
    return QCoreApplication.translate(
        'FileManagerForm',
        'Listing MFS path: {0}').format(path)


def iSearchFoundFile(name):
    return QCoreApplication.translate(
        'FileManagerForm',
        'Search matched file with name: {0}').format(name)


def iListingMFSTimeout(path):
    return QCoreApplication.translate(
        'FileManagerForm',
        'Timeout while listing MFS path: {0}').format(path)


def iOpenWith():
    return QCoreApplication.translate('FileManagerForm', 'Open with')


def iDeleteFileOrDir():
    return QCoreApplication.translate(
        'FileManagerForm', 'Delete file/directory')


def iUnlinkFileOrDir():
    return QCoreApplication.translate(
        'FileManagerForm', 'Unlink file/directory')


def iHashmarkFile():
    return QCoreApplication.translate('FileManagerForm', 'Hashmark')


def iBrowseFile():
    return QCoreApplication.translate('FileManagerForm', 'Browse')


def iSelectDirectory():
    return QCoreApplication.translate('FileManagerForm', 'Select directory')


def iSelectFiles():
    return QCoreApplication.translate('FileManagerForm',
                                      'Select one or more files to import')


def iOfflineMode():
    return QCoreApplication.translate('FileManagerForm', 'Offline mode')


def iChunker():
    return QCoreApplication.translate('FileManagerForm', 'Chunker')


def iHashFunction():
    return QCoreApplication.translate('FileManagerForm', 'Hash function')


def iDhtProvide():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Announce (DHT provide)')


def iDhtProvideRecursive():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Announce (DHT provide, recursive)')


def iRawBlocksForLeaves():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Use raw blocks for leaf nodes')


def iUseFilestore():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Use filestore if available')


def iUseTimeMetadata():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Use time metadata (MFS linking)')


def iDAGGenerationFormat():
    return QCoreApplication.translate(
        'FileManagerForm',
        'DAG generation format')


def iDAGFormatBalanced():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Balanced')


def iDAGFormatTrickle():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Trickle')


def iOfflineModeToolTip():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Offline mode: in this mode your files will not be '
        'immediately announced on the DHT')


def iSearchFilesHelp():
    return QCoreApplication.translate(
        'FileManagerForm',
        'Search your files (regular expression)'
    )


class MFSTreeView(QTreeView):
    def mousePressEvent(self, event):
        item = self.indexAt(event.pos())

        if item.isValid():
            super(MFSTreeView, self).mousePressEvent(event)
        else:
            self.clearSelection()

            self.selectionModel().setCurrentIndex(
                QModelIndex(),
                QItemSelectionModel.Select
            )

    def resizeEvent(self, event):
        self.header().setMinimumSectionSize(
            self.size().width() / 3)
        self.header().setMaximumSectionSize(
            self.size().width() / 2)
        super().resizeEvent(event)


class CustomSortFilterProxyModel(QSortFilterProxyModel):
    def filterAcceptsRow(self, sourceRow, sourceParent):
        return False


class TimeFrameSelectorWidget(QWidget):
    datesChanged = AsyncSignal(QDate, QDate)

    def __init__(self, parent=None):
        super(TimeFrameSelectorWidget, self).__init__(
            parent)

        self.app = QApplication.instance()

        self.ui = ui_timeframeselector.Ui_TimeFrameSelector()
        self.ui.setupUi(self)

        self.ui.tfIconLabel.setPixmap(
            QPixmap.fromImage(
                QImage(':/share/icons/clock.png')
            ).scaledToWidth(32)
        )

        self.ui.dateTo.setDate(self.today().addDays(14))
        self.ui.dateFrom.setDate(self.today().addDays(
            -(30 * 3)))

        self.ui.dateFrom.dateChanged.connect(self.onDateFromChanged)
        self.ui.dateTo.dateChanged.connect(self.onDateToChanged)
        self.ui.mfsTimeMetadata.setChecked(
            self.app.settingsMgr.isTrue(
                CFG_SECTION_FILEMANAGER,
                CFG_KEY_TIME_METADATA
            )
        )
        self.ui.mfsTimeMetadata.stateChanged.connect(
            self.onTimeMetadataToggled
        )

    @property
    def useTimeMetadata(self):
        return self.ui.mfsTimeMetadata.checkState() == Qt.Checked

    def onTimeMetadataToggled(self, state):
        self.app.settingsMgr.setBoolFrom(
            CFG_SECTION_FILEMANAGER,
            CFG_KEY_TIME_METADATA,
            state == Qt.Checked
        )

    def onDateFromChanged(self, date):
        if date > self.ui.dateTo.date():
            return messageBox('Invalid start date')

        ensure(self.datesChanged.emit(date, self.ui.dateTo.date()))

    def onDateToChanged(self, date):
        if date < self.ui.dateFrom.date():
            return messageBox('Invalid end date')

        ensure(self.datesChanged.emit(self.ui.dateFrom.date(), date))

    def qDateToDate(self, _date):
        return date(
            _date.year(),
            _date.month(),
            _date.day()
        )

    @property
    def dateFrom(self):
        return self.qDateToDate(self.ui.dateFrom.date())

    @property
    def dateTo(self):
        return self.qDateToDate(self.ui.dateTo.date())

    def today(self):
        return QDate.currentDate()


class FileManager(QWidget):
    statusReady = 0
    statusBusy = 1

    displayedItemChanged = pyqtSignal(MFSNameItem)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()

        self.lock = asyncio.Lock()
        self.model = None
        self._offlineMode = False
        self._importTask = None

        self.ui = ui_files.Ui_FileManagerForm()
        self.ui.setupUi(self)

        self.hashFunction = 'sha2-256'
        self.mfsMetadataRe = re.compile(
            r'_mfsmeta_(?P<time>\d*)_(?P<mtime>\d*)' +
            r'_(?P<size>\d*)_(?P<name>.*)$'
        )

        # Build file browser
        self.displayedItem = None
        self.createFileManager()

        self.timeFrameSelector = TimeFrameSelectorWidget()
        self.timeFrameSelector.datesChanged.connectTo(
            self.onTimeFrameChanged)
        self.timeFrameSelector.hide()

        self.ui.hLayoutTimeFrame.addWidget(self.timeFrameSelector)

        self.filesDialog = QFileDialog(None)
        self.dialogLastDirSelected = None

        self.ui.localFileManagerSwitch.setCheckable(True)

        self.busyCube = AnimatedLabel(
            RotatingCubeRedFlash140d(speed=100),
            parent=self
        )
        self.busyCube.clip.setScaledSize(QSize(24, 24))
        self.busyCube.hide()

        self.ui.datesPickButton.toggled.connect(self.onDatePickToggled)
        self.ui.refreshButton.setShortcut(QKeySequence('Ctrl+r'))

        self.ui.fsControlLayout.insertWidget(0, self.busyCube)

        # Connect the various buttons
        self.ui.helpButton.clicked.connect(
            lambda: self.app.manuals.browseManualPage('filemanager.html'))
        self.ui.addFileButton.clicked.connect(self.onAddFilesClicked)
        self.ui.addDirectoryButton.clicked.connect(self.onAddDirClicked)
        self.ui.refreshButton.clicked.connect(self.onRefreshClicked)
        self.ui.searchFiles.returnPressed.connect(
            partialEnsure(self.onSearchFiles))
        self.ui.searchFiles.setToolTip(iSearchFilesHelp())
        self.ui.localFileManagerSwitch.toggled.connect(
            self.onLocalFileManagerToggled)
        self.ui.fileManagerButton.clicked.connect(self.onLocalFileManager)
        self.ui.cancelButton.hide()
        self.ui.cancelButton.clicked.connect(self.onCancelOperation)

        # FS options button
        fsOptsMenu = QMenu(self)
        fsDagFormatMenu = QMenu(iDAGGenerationFormat(), self)
        fsDagFormatMenu.setIcon(getIcon('ipld.png'))

        fsIconSizeMenu = QMenu('Icon size', self)
        self.iconSizeGroup = QActionGroup(fsIconSizeMenu)
        self.iconSizeGroup.triggered.connect(self.onIconSize)
        self.actionSmallIcon = QAction('Small', self.iconSizeGroup)
        self.actionSmallIcon.setCheckable(True)
        self.actionSmallIcon.setChecked(True)
        self.actionMediumIcon = QAction('Medium', self.iconSizeGroup)
        self.actionMediumIcon.setCheckable(True)
        self.actionLargeIcon = QAction('Large', self.iconSizeGroup)
        self.actionLargeIcon.setCheckable(True)
        self.iconSizeGroup.addAction(self.actionSmallIcon)
        self.iconSizeGroup.addAction(self.actionMediumIcon)
        self.iconSizeGroup.addAction(self.actionLargeIcon)
        fsIconSizeMenu.addActions(self.iconSizeGroup.actions())

        fsChunkerMenu = self.buildChunkerMenu()
        fsHashFuncMenu = self.buildHashFuncMenu()

        fsMiscOptsMenu = QMenu('Options', self)
        fsMiscOptsMenu.setIcon(getIcon('folder-black.png'))

        self.rawLeavesAction = QAction(
            iRawBlocksForLeaves(), fsMiscOptsMenu)
        self.rawLeavesAction.setCheckable(True)
        self.fileStoreAction = QAction(
            iUseFilestore(), fsMiscOptsMenu)
        self.fileStoreAction.setCheckable(True)

        fsMiscOptsMenu.addAction(self.rawLeavesAction)
        fsMiscOptsMenu.addAction(self.fileStoreAction)

        self.dagFormatGroup = QActionGroup(fsDagFormatMenu)
        self.dagFormatGroup.triggered.connect(self.onDagFormatChanged)

        self.dagFormatBalancedAction = QAction(
            iDAGFormatBalanced(), self.dagFormatGroup)
        self.dagFormatBalancedAction.setCheckable(True)
        self.dagFormatBalancedAction.setChecked(True)
        self.dagFormatTrickleAction = QAction(
            iDAGFormatTrickle(), self.dagFormatGroup)
        self.dagFormatTrickleAction.setCheckable(True)

        self.dagFormatGroup.addAction(self.dagFormatBalancedAction)
        self.dagFormatGroup.addAction(self.dagFormatTrickleAction)

        fsDagFormatMenu.addActions(self.dagFormatGroup.actions())

        fsOptsMenu.addMenu(fsDagFormatMenu)
        fsOptsMenu.addSeparator()
        fsOptsMenu.addMenu(fsChunkerMenu)
        fsOptsMenu.addSeparator()
        fsOptsMenu.addMenu(fsHashFuncMenu)
        fsOptsMenu.addSeparator()
        fsOptsMenu.addMenu(fsMiscOptsMenu)
        fsOptsMenu.addSeparator()
        fsOptsMenu.addMenu(fsIconSizeMenu)

        self.ui.fsOptionsButton.setPopupMode(QToolButton.InstantPopup)
        self.ui.fsOptionsButton.setMenu(fsOptsMenu)

        # Offline mode button
        self.ui.offlineButton.setObjectName('filemanagerOfflineButton')
        self.ui.offlineButton.setText(iOfflineMode())
        self.ui.offlineButton.setCheckable(True)
        self.ui.offlineButton.toggled.connect(self.onOfflineToggle)
        self.ui.offlineButton.setChecked(False)
        self.ui.offlineButton.setVisible(False)

        self.mfsTree = MFSTreeView()
        self.ui.hLayoutFilesView.insertWidget(0, self.mfsTree)

        # Connect the tree view actions
        self.mfsTree.doubleClicked.connect(self.onDoubleClicked)
        self.mfsTree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mfsTree.customContextMenuRequested.connect(
            self.onContextMenu)
        self.mfsTree.expanded.connect(self.onExpanded)
        self.mfsTree.collapsed.connect(self.onCollapsed)
        self.mfsTree.header().setVisible(False)
        self.mfsTree.setObjectName('mfsTreeView')
        self.mfsTree.header().setMinimumSectionSize(400)

        self.ui.collapseAll.clicked.connect(self.onCollapseAll)
        self.ui.collapseAll.hide()

        # Connect the event filter
        evfilter = IPFSTreeKeyFilter(self.mfsTree)
        evfilter.copyHashPressed.connect(self.onCopyItemHash)
        evfilter.copyPathPressed.connect(self.onCopyItemPath)
        evfilter.returnPressed.connect(self.onReturn)
        evfilter.explorePressed.connect(self.onExploreItem)
        self.mfsTree.installEventFilter(evfilter)

        self.displayedItemChanged.connect(self.onItemChange)

        # Setup the tree view
        self.mfsTree.setExpandsOnDoubleClick(True)
        self.mfsTree.setItemsExpandable(True)
        self.mfsTree.setSortingEnabled(True)

        self.iconFolder = getIcon('folder-open.png')
        self.iconFile = getIcon('file.png')

        # Configure drag-and-drop
        self.mfsTree.setAcceptDrops(True)
        self.mfsTree.setDragDropMode(QAbstractItemView.DragDrop)

        self.ipfsKeys = []
        self.busy(False)

    @property
    def gWindow(self):
        return self.app.mainWindow

    @property
    def mfsSelModel(self):
        return self.mfsTree.selectionModel()

    @property
    def profile(self):
        return self.app.ipfsCtx.currentProfile

    @property
    def offlineMode(self):
        if self.displayedItem:
            return self.displayedItem.offline

        return self._offlineMode

    @property
    def dagGenerationFormat(self):
        cAction = self.dagFormatGroup.checkedAction()
        if cAction is self.dagFormatBalancedAction:
            return 'balanced'
        elif cAction is self.dagFormatTrickleAction:
            return 'trickle'
        return 'unknown'

    @property
    def useRawLeaves(self):
        return self.rawLeavesAction.isChecked()

    @property
    def useFileStore(self):
        return self.fileStoreAction.isChecked()

    @property
    def displayPath(self):
        if self.displayedItem:
            return self.displayedItem.path

    @property
    def tfDateFrom(self):
        return self.timeFrameSelector.dateFrom

    @property
    def tfDateTo(self):
        return self.timeFrameSelector.dateTo

    @property
    def isBusy(self):
        return self.status == self.statusBusy

    def busy(self, busy=True, showClip=False):
        if busy:
            self.status = self.statusBusy
        else:
            self.status = self.statusReady

        self.mfsTree.setEnabled(not busy)
        self.ui.addFileButton.setEnabled(not busy)
        self.ui.addDirectoryButton.setEnabled(not busy)
        self.ui.refreshButton.setEnabled(not busy)
        self.ui.searchFiles.setEnabled(not busy)
        self.ui.fileManagerButton.setEnabled(not busy)
        self.ui.localFileManagerSwitch.setEnabled(not busy)
        self.ui.fsOptionsButton.setEnabled(not busy)
        self.ui.pathSelector.setEnabled(not busy)
        self.ui.datesPickButton.setEnabled(not busy)

        if busy and showClip:
            self.busyCube.setVisible(busy)
            self.busyCube.startClip()
            self.busyCube.clip.setSpeed(150)
        else:
            self.busyCube.setVisible(False)
            self.busyCube.stopClip()

    @property
    def rscOpenTryDecrypt(self):
        return self.displayedItem is self.model.itemEncrypted or \
            self.displayedItem is self.model.itemQrCodes

    @property
    def inEncryptedFolder(self):
        return self.displayedItem is self.model.itemEncrypted

    def buildHashFuncMenu(self):
        # Build the menu to select the hashing function

        fsHashMenu = QMenu(iHashFunction(), self)
        self.hashFnGroup = QActionGroup(fsHashMenu)
        self.hashFnGroup.triggered.connect(self.onHashFunctionChanged)

        # One day probably just call /api/vx/cid/hashes and filter but hey..
        hFnList = ['sha1']
        hFnList += ['sha2-256', 'sha2-512']
        hFnList += ['sha3-512', 'sha2-512']
        hFnList += ['dbl-sha2-256']
        hFnList += ['keccak-{}'.format(x) for x in [256, 512]]
        hFnList += ['blake2b-{}'.format(x) for x in range(160, 513, 32)]
        hFnList += ['blake2s-{}'.format(x) for x in range(160, 257, 32)]

        for func in hFnList:
            action = QAction(func, self.hashFnGroup)
            action.setCheckable(True)

            if func == 'sha2-256':
                action.setChecked(True)

        fsHashMenu.addActions(self.hashFnGroup.actions())
        return fsHashMenu

    def buildChunkerMenu(self):
        # Build the menu to select the chunking strategy
        fsChunkerMenu = QMenu(iChunker(), self)

        self.chunkingAlg = 'size-262144'
        self.chunkerGroup = QActionGroup(fsChunkerMenu)
        self.chunkerGroup.triggered.connect(self.onChunkerChanged)

        # Fixed block size algorithm
        sizes = [int(32768 * x) for x in range(4, 32, 4)]

        for size in sizes:
            action = QAction('Fixed-size chunker (block size: {} kb)'.format(
                int(size / 1024)), self.chunkerGroup)
            action.setData('size-{}'.format(size))
            action.setCheckable(True)

            # Check the default chunker
            if size == 262144:
                action.setChecked(True)

        # Rabin.
        # This is just a small selection of block sizes people might
        # want to try. For each minimum block size we calculate a number
        # of maximum block sizes (the average is always the median value)

        msizes = [int(32768 * x) for x in range(2, 16, 2)]

        for msize in msizes:
            maxsizes = [int(msize * z) for z in range(2, 6, 1)]

            for maxs in maxsizes:
                if maxs >= (1024 * 1024):
                    break

                avgs = msize + int((maxs - msize) / 2)

                action = QAction(
                    'Rabin chunker '
                    '(min: {mbs} kb, avg: {avgbs} kb, max: {maxbs} kb)'.format(
                        mbs=int(msize / 1024),
                        avgbs=int(avgs / 1024),
                        maxbs=int(maxs / 1024)
                    ), self.chunkerGroup
                )

                action.setCheckable(True)
                action.setData('rabin-{0}-{1}-{2}'.format(msize, avgs, maxs))

        fsChunkerMenu.addActions(self.chunkerGroup.actions())
        return fsChunkerMenu

    def sortMfsTree(self, enabled=True, order=Qt.AscendingOrder):
        self.mfsTree.setSortingEnabled(enabled)
        self.mfsTree.sortByColumn(0, order)

    def createFileManager(self):
        self.fManagerModel = QFileSystemModel()
        self.fManagerModel.setRootPath('')

        self.localTree = QTreeView()
        self.localTree.setModel(self.fManagerModel)
        self.localTree.setDragEnabled(True)
        self.localTree.setDragDropMode(QAbstractItemView.DragOnly)
        self.localTree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.localTree.setItemsExpandable(True)

        rootIndex = self.fManagerModel.index(QDir.rootPath())
        if rootIndex.isValid():
            self.localTree.setRootIndex(rootIndex)

        if self.app.system in ['Linux', 'FreeBSD', 'Darwin']:
            """
            Expand the user's home folder and its parents
            """

            home = QDir(QDir.homePath())
            myHomeIndex = self.fManagerModel.index(home.path())

            if myHomeIndex.isValid():
                self.localTree.expand(myHomeIndex)

                while home.cdUp():
                    idx = self.fManagerModel.index(home.path())
                    if idx.isValid():
                        self.localTree.expand(idx)

        for col in range(1, 4):
            self.localTree.hideColumn(col)

        self.localTree.hide()
        self.ui.hLayoutBrowser.insertWidget(0, self.localTree)

    def setupPathSelector(self):
        def c():
            return self.ui.pathSelector.count()

        self.ui.pathSelector.clear()

        self.ui.pathSelector.setObjectName('fmanagerPathSelector')
        self.ui.pathSelector.insertItem(c(), self.model.itemHome.icon(),
                                        'Home')
        self.ui.pathSelector.insertSeparator(c())
        self.ui.pathSelector.insertItem(c(), self.model.itemImages.icon(),
                                        iImages())
        self.ui.pathSelector.insertItem(c(),
                                        self.model.itemPictures.icon(),
                                        iPictures())
        self.ui.pathSelector.insertItem(c(), self.model.itemVideos.icon(),
                                        iVideos())
        self.ui.pathSelector.insertItem(c(), self.model.itemMusic.icon(),
                                        iMusic())
        self.ui.pathSelector.insertSeparator(c())
        self.ui.pathSelector.insertItem(c(), self.model.itemCode.icon(),
                                        iCode())
        self.ui.pathSelector.insertItem(c(),
                                        self.model.itemDocuments.icon(),
                                        iDocuments())
        self.ui.pathSelector.insertSeparator(c())
        self.ui.pathSelector.insertItem(c(),
                                        self.model.itemWebPages.icon(),
                                        iWebPages())
        self.ui.pathSelector.insertItem(c(),
                                        self.model.itemDWebApps.icon(),
                                        iDWebApps())
        self.ui.pathSelector.insertSeparator(c())
        self.ui.pathSelector.insertItem(c(),
                                        self.model.itemQrCodes.icon(),
                                        iQrCodes())
        self.ui.pathSelector.insertSeparator(c())
        self.ui.pathSelector.insertItem(c(),
                                        self.model.itemTemporary.icon(),
                                        iTemporaryFiles())
        self.ui.pathSelector.insertSeparator(c())
        self.ui.pathSelector.insertItem(c(),
                                        self.model.itemEncrypted.icon(),
                                        iEncryptedFiles())
        self.ui.pathSelector.activated.connect(self.onPathSelector)

        if self.app.system == 'Linux':
            self.ui.pathSelector.setIconSize(QSize(24, 24))

    def setupModel(self):
        if self.profile is None:
            return

        # Setup the model if needed
        if self.model is None and self.profile.filesModel:
            self.model = self.profile.filesModel

            if not self.model.qrInitialized:
                ensure(self.model.setupQrCodesFolder(
                    self.profile, self.model, self))

        if not self.model:
            return

        self.mfsTree.setModel(self.model)
        self.mfsTree.header().setSectionResizeMode(
            QHeaderView.ResizeToContents)

        if self.displayedItem is None:
            self.changeDisplayItem(self.model.itemHome)

        self.app.task(self.updateKeys)

        self.disconnectDropSignals()

        # Connect the model's drag-and-drop signals
        self.model.fileDropEvent.connect(self.onDropFile)
        self.model.directoryDropEvent.connect(self.onDropDirectory)

        if self.ui.pathSelector.count() == 0:
            self.setupPathSelector()

    def enableButtons(self, flag=True):
        for btn in [self.ui.addFileButton,
                    self.ui.addDirectoryButton,
                    self.ui.refreshButton,
                    self.ui.localFileManagerSwitch,
                    self.ui.fileManagerButton,
                    self.ui.fsOptionsButton,
                    self.ui.pathSelector,
                    self.ui.offlineButton,
                    self.ui.searchFiles]:
            btn.setEnabled(flag)

        if self.model and self.displayedItem is self.model.itemEncrypted:
            self.ui.addDirectoryButton.setEnabled(False)

    def showCancel(self, show=True):
        self.ui.cancelButton.setVisible(show)
        if show is False:
            self._importTask = None

    def currentItem(self):
        currentIdx = self.mfsTree.currentIndex()
        if currentIdx.isValid():
            return self.model.getNameItemFromIdx(currentIdx)

    def onDatePickToggled(self, toggled):
        self.timeFrameSelector.setVisible(toggled)

    async def onTimeFrameChanged(self, dateFrom, dateTo):
        self.updateTree(timeFrameUpdate=True)

    def onDagFormatChanged(self, action):
        pass

    def onChunkerChanged(self, action):
        self.chunkingAlg = action.data()

    def onHashFunctionChanged(self, action):
        self.hashFunction = action.text()

    def onIconSize(self, action):
        if action is self.actionSmallIcon:
            size = QSize(16, 16)
        elif action is self.actionMediumIcon:
            size = QSize(24, 24)
        elif action is self.actionLargeIcon:
            size = QSize(32, 32)
        else:
            return

        self.app.settingsMgr.setSetting(
            CFG_SECTION_FILEMANAGER,
            CFG_KEY_ICONSIZE,
            action.text().lower()
        )

        self.mfsTree.setIconSize(size)

    def onCollapseAll(self):
        self.mfsTree.collapseAll()

        if self.displayedItem:
            self.displayedItem.expandedItemsCount = 0
            self.collapseButtonUpdate()

    def onOfflineToggle(self, checked):
        if self.displayedItem:
            self.displayedItem.offline = checked

        self.ui.offlineButton.setToolTip(iOfflineModeToolTip())

    async def onClose(self):
        if not self.isBusy:
            self.disconnectDropSignals()
            return True
        return False

    def onItemChange(self, item):
        self.collapseButtonUpdate()

        if isinstance(item, MFSRootItem):
            self.ui.offlineButton.setChecked(item.offline)

    def collapseButtonUpdate(self):
        self.ui.collapseAll.setVisible(
            self.displayedItem.expandedItemsCount > 0)

    def disconnectDropSignals(self):
        try:
            self.model.fileDropEvent.disconnect(self.onDropFile)
            self.model.directoryDropEvent.disconnect(self.onDropDirectory)
        except Exception:
            pass

    def onLocalFileManagerToggled(self, checked):
        self.localTree.setVisible(checked)

    def onLocalFileManager(self):
        self.ui.localFileManagerSwitch.setChecked(
            not self.ui.localFileManagerSwitch.isChecked())

    def onDropFile(self, path):
        async def _handle():
            mfsDlg = self._createMfsOptionsDialog()

            options = await self.runMfsDialog(mfsDlg)
            if options:
                await self.scheduleAddFiles([path], options)

        ensure(_handle())

    def onDropDirectory(self, path):
        async def _handle():
            mfsDlg = self._createMfsOptionsDialog(type='dir')

            options = await self.runMfsDialog(mfsDlg)
            if options:
                await self.scheduleAddDirectory(path, options)

        ensure(_handle())

    def onCopyItemHash(self):
        currentItem = self.currentItem()
        if currentItem:
            dataHash = self.model.getHashFromIdx(currentItem.index())
            self.app.setClipboardText(dataHash)

    def onCopyItemPath(self):
        currentItem = self.currentItem()
        if currentItem:
            nameItem = self.model.getNameItemFromIdx(currentItem.index())
            if nameItem:
                self.app.setClipboardText(nameItem.fullPath)

    def onReturn(self):
        currentItem = self.currentItem()
        dataHash = self.model.getHashFromIdx(currentItem.index())
        if dataHash:
            self.gWindow.addBrowserTab().browseIpfsHash(dataHash)

    def onExpanded(self, idx):
        if self.displayedItem and idx != self.displayedItem.index():
            self.displayedItem.expandedItemsCount += 1
            self.collapseButtonUpdate()

    def onCollapsed(self, idx):
        if self.displayedItem and idx != self.displayedItem.index():
            self.displayedItem.expandedItemsCount -= 1
            self.collapseButtonUpdate()

    def pathSelectorDefault(self):
        self.ui.pathSelector.setCurrentIndex(0)

    def onPathSelector(self, idx):
        if self.isBusy:
            return

        text = self.ui.pathSelector.itemText(idx)

        if text == iHome():
            self.changeDisplayItem(self.model.itemHome)
        elif text == iPictures():
            self.changeDisplayItem(self.model.itemPictures)
        elif text == iImages():
            self.changeDisplayItem(self.model.itemImages)
        elif text == iVideos():
            self.changeDisplayItem(self.model.itemVideos)
        elif text == iMusic():
            self.changeDisplayItem(self.model.itemMusic)
        elif text == iCode():
            self.changeDisplayItem(self.model.itemCode)
        elif text == iDocuments():
            self.changeDisplayItem(self.model.itemDocuments)
        elif text == iWebPages():
            self.changeDisplayItem(self.model.itemWebPages)
        elif text == iDWebApps():
            self.changeDisplayItem(self.model.itemDWebApps)
        elif text == iQrCodes():
            self.changeDisplayItem(self.model.itemQrCodes)
        elif text == iTemporaryFiles():
            self.changeDisplayItem(self.model.itemTemporary)
        elif text == iEncryptedFiles():
            self.changeDisplayItem(self.model.itemEncrypted)

    def refreshItem(self, item):
        self.app.task(self.listFiles, item.path,
                      parentItem=item, maxdepth=1)

    def changeDisplayItem(self, item):
        self.displayedItem = item
        self.mfsTree.setRootIndex(self.displayedItem.index())
        self.updateTree()
        self.mfsTree.expand(self.displayedItem.index())

        if isinstance(item, MFSRootItem):
            self.displayedItemChanged.emit(item)

    def onContextMenuVoid(self, point):
        menu = QMenu(self)
        menu.exec(self.mfsTree.mapToGlobal(point))

    def onContextMenu(self, point):
        idx = self.mfsTree.indexAt(point)
        if not idx.isValid():
            return self.onContextMenuVoid(point)

        item = self.model.itemFromIndex(idx)

        if not isinstance(item, MFSNameItem):
            return

        nameItem = self.model.getNameItemFromIdx(idx)
        dataHash = self.model.getHashFromIdx(idx)
        ipfsPath = nameItem.ipfsPath
        menu = QMenu(self)
        actionsMenu = QMenu('Object', menu)
        actionsMenu.setIcon(getIcon('ipfs-logo-128-white.png'))
        pyrDropButton = self.app.mainWindow.getPyrDropButtonFor(ipfsPath)

        def explore(cid):
            self.gWindow.explore(cid)

        def hashmark(mPath, name):
            ensure(addHashmarkAsync(mPath, name))

        def copyHashToClipboard(itemHash):
            self.app.appClipboard.setText(itemHash)

        def openWithMediaPlayer(itemHash):
            parentHash = nameItem.parentHash
            name = nameItem.entry['Name']
            if parentHash:
                fp = joinIpfs(os.path.join(parentHash, name))
                self.gWindow.mediaPlayerPlay(fp, mediaName=name)
            else:
                self.gWindow.mediaPlayerPlay(joinIpfs(itemHash),
                                             mediaName=name)

        menu.addAction(getIcon('clipboard.png'),
                       iCopyCIDToClipboard(),
                       functools.partial(self.app.setClipboardText, dataHash))
        if nameItem.fullPath:
            menu.addAction(getIcon('clipboard.png'),
                           iCopyPathToClipboard(),
                           functools.partial(self.app.setClipboardText,
                                             str(ipfsPath)))

        menu.addAction(getIcon('clipboard.png'),
                       iCopyPubGwUrlToClipboard(),
                       functools.partial(
                           self.app.setClipboardText,
                           ipfsPath.publicGwUrl
        ))

        menu.addSeparator()
        actionsMenu.addAction(
            getIconIpfs64(),
            iDhtProvide(),
            functools.partial(
                self.onDhtProvide,
                dataHash,
                False))
        actionsMenu.addAction(
            getIconIpfs64(),
            iDhtProvideRecursive(),
            functools.partial(
                self.onDhtProvide,
                dataHash,
                True))
        actionsMenu.addSeparator()

        actionsMenu.addAction(getIcon('ipld.png'), iDagView(),
                              functools.partial(self.onDagView, dataHash))
        actionsMenu.addSeparator()

        actionsMenu.addAction(getIcon('hashmarks.png'),
                              iHashmarkFile(),
                              functools.partial(hashmark, str(ipfsPath),
                                                nameItem.entry['Name']))
        actionsMenu.addAction(getIconIpfs64(),
                              iBrowseFile(),
                              functools.partial(self.browse, str(ipfsPath)))
        actionsMenu.addAction(
            getIcon('open.png'),
            iOpen(),
            functools.partial(
                ensure,
                self.app.resourceOpener.open(
                    str(ipfsPath),
                    openingFrom='filemanager',
                    tryDecrypt=self.rscOpenTryDecrypt)))

        if nameItem.isFile() or nameItem.isDir():
            actionsMenu.addAction(getIcon('text-editor.png'),
                                  iEditObject(),
                                  functools.partial(self.editObject,
                                                    ipfsPath))

        if nameItem.isDir():
            actionsMenu.addAction(getIcon('folder-open.png'),
                                  iExploreDirectory(),
                                  functools.partial(explore, dataHash))

        def publishToKey(action):
            key = action.data()['key']['Name']
            oHash = action.data()['hash']

            async def publish(op, oHash, keyName):
                await op.publish(joinIpfs(oHash), key=keyName)

            self.app.ipfsTaskOp(publish, oHash, key)

        # Media player actions
        if nameItem.isFile():
            actionsMenu.addAction(
                getIcon('multimedia.png'),
                iMediaPlayerQueue(), partialEnsure(
                    self.mediaPlayerQueueFile, str(ipfsPath)))
        elif nameItem.isDir():
            actionsMenu.addAction(
                getIcon('multimedia.png'),
                iMediaPlayerQueue(), partialEnsure(
                    self.mediaPlayerQueueDir, str(ipfsPath)))

        actionsMenu.addSeparator()
        actionsMenu.addAction(getIcon('pin.png'),
                              iUnpin(),
                              partialEnsure(self.unpinObject, dataHash)
                              )

        menu.addMenu(actionsMenu)

        menu.addSeparator()

        menu.addMenu(pyrDropButton.menu)
        menu.addSeparator()

        # Delete/unlink
        menu.addSeparator()
        menu.addAction(
            getIcon('clear-all.png'),
            iUnlinkFileOrDir(), partialEnsure(
                self.scheduleUnlink, nameItem, dataHash))
        menu.addAction(
            getIcon('clear-all.png'),
            iDeleteFileOrDir(), partialEnsure(
                self.scheduleDelete, nameItem, dataHash))
        menu.addSeparator()

        # Populate publish menu
        publishMenu = QMenu('Publish to IPNS key', self)
        publishMenu.setIcon(getIcon('key-diago.png'))
        for key in self.ipfsKeys:
            if not key['Name'] or key['Name'].startswith(GALACTEEK_NAME):
                continue

            action = QAction(key['Name'], self)
            action.setData({
                'key': key,
                'hash': dataHash
            })

            publishMenu.addAction(action)

        publishMenu.triggered.connect(publishToKey)
        ensure(self.buildDidPublishMenu(menu, str(ipfsPath)))

        menu.addSeparator()
        menu.addMenu(publishMenu)

        menu.exec(self.mfsTree.mapToGlobal(point))

    @ipfsOp
    async def buildDidPublishMenu(self, ipfsop, menu, ipfsPath):
        profile = ipfsop.ctx.currentProfile

        # DID publishing menu
        try:
            didPublishMenu = await buildPublishingMenu(
                await profile.userInfo.ipIdentifier(),
                parent=menu
            )
            didPublishMenu.triggered.connect(
                functools.partial(self.onDidPublish, ipfsPath)
            )
        except Exception:
            pass
        else:
            menu.addMenu(didPublishMenu)

    def onDidPublish(self, objPath, action):
        data = action.data()
        service = data['service']

        ipfsPath = IPFSPath(objPath, autoCidConv=True)
        if not ipfsPath.valid:
            return

        ensure(self.publishObjectOnDidService(service, ipfsPath))

    @ipfsOp
    async def unpinObject(self, ipfsop, cid):
        await ipfsop.unpin(cid)

    async def publishObjectOnDidService(self, service, ipfsPath):
        if service.type == IPService.SRV_TYPE_COLLECTION:
            await service.add(str(ipfsPath))

    @ipfsOp
    async def mediaPlayerQueueDir(self, ipfsop, ipfsPath):
        async for objPath, parent in ipfsop.walk(str(ipfsPath)):
            await self.mediaPlayerQueueFile(objPath)

    @ipfsOp
    async def mediaPlayerQueueFile(self, ipfsop, objPath):
        mType, stat = await self.app.rscAnalyzer(objPath)
        if not mType:
            return

        if mType.isAudio or mType.isVideo:
            self.app.mainWindow.mediaPlayerQueue(objPath)

    def browse(self, path):
        self.gWindow.addBrowserTab().browseFsPath(
            IPFSPath(path, autoCidConv=True))

    def onDagView(self, cid):
        view = dag.DAGViewer(joinIpfs(cid), self.app.mainWindow)
        self.app.mainWindow.registerTab(
            view, iDagViewer(),
            current=True,
            icon=getIcon('ipld.png'),
            tooltip=cid
        )

    def onDhtProvide(self, cid, recursive):
        @ipfsOpFn
        async def dhtProvide(ipfsop, value, recursive=True):
            if await ipfsop.provide(value, recursive=recursive) is True:
                logUser.info('{0}: DHT provide OK!'.format(value))
            else:
                logUser.info('{0}: DHT provide error'.format(value))

        ensure(dhtProvide(cid, recursive=recursive))

    def editObject(self, ipfsPath):
        self.gWindow.addEditorTab(path=ipfsPath)

    def onExploreItem(self):
        current = self.currentItem()

        if current and current.isDir():
            dataHash = self.model.getHashFromIdx(current.index())
            self.gWindow.explore(dataHash)

    def onDoubleClicked(self, idx):
        resourceOpener = self.gWindow.app.resourceOpener

        if not idx.isValid():
            return

        item = self.model.itemFromIndex(idx)

        if not isinstance(item, MFSNameItem):
            return

        nameItem = self.model.getNameItemFromIdx(idx)

        dataHash = self.model.getHashFromIdx(idx)

        if nameItem.isFile():
            fileName = nameItem.text()
            finalPath = joinIpfs(dataHash)

            # Find the parent hash
            parentHash = nameItem.parentHash
            if parentHash:
                # We have the parent hash, so use it to build a file path
                # preserving the real file name
                finalPath = joinIpfs(os.path.join(parentHash, fileName))

            ensure(resourceOpener.open(
                finalPath,
                openingFrom='filemanager',
                tryDecrypt=self.rscOpenTryDecrypt
            ))

        elif nameItem.isDir():
            self.app.task(self.listFiles, item.path, parentItem=item,
                          autoexpand=True)

    def expandIndexBackwards(self, idx, scroll=False):
        while idx.isValid():
            if not self.mfsTree.isExpanded(idx):
                self.mfsTree.expand(idx)

            if scroll:
                self.mfsTree.scrollTo(idx, QAbstractItemView.PositionAtCenter)

            idx = idx.parent()

    async def onSearchFiles(self):
        searchQuery = self.ui.searchFiles.text()

        if searchQuery:
            try:
                rec = re.compile(searchQuery)
            except re.error:
                return messageBox('Invalid expression')

            self.mfsSelModel.clearSelection()

            # List everything (no depth limit)
            await self.listFiles(self.displayPath,
                                 parentItem=self.displayedItem, maxdepth=0,
                                 timeout=60,
                                 subTask=False)

            self.busy(True)

            # Run the search
            await self.runSearch(rec)

            self.busy(False)

        self.ui.searchFiles.setFocus(Qt.OtherFocusReason)

    async def runSearch(self, rec, index=None):
        idx = index if index else self.displayedItem.index()
        caseIdx = self.ui.comboSearchCase.currentIndex()

        reflags = re.IGNORECASE if caseIdx == 1 else 0

        async for idx, data in modelhelpers.modelWalkAsync(
            self.model, searchre=rec,
            reflags=reflags,
            parent=idx,
            role=self.model.FileNameRole,
            columns=[0]
        ):
            self.expandIndexBackwards(idx)
            self.mfsSelModel.select(
                idx,
                QItemSelectionModel.Select | QItemSelectionModel.Rows
            )

            self.statusSet(iSearchFoundFile(data))

    def onMkDirClicked(self):
        dirName = QInputDialog.getText(self, 'Directory name',
                                       'Directory name')
        if dirName:
            self.app.task(self.makeDir, self.displayedItem.path,
                          dirName[0])

    def onRefreshClicked(self):
        self.updateTree(timeFrameUpdate=True)
        self.mfsTree.setFocus(Qt.OtherFocusReason)

    def onAddDirClicked(self):
        dialog = QFileDialog(None)

        dialog.setFileMode(QFileDialog.DirectoryOnly)
        dialog.filesSelected.connect(
            lambda dirs: ensure(self.onDirsSelected(dialog, dirs)))

        return dialog.exec_()

    async def runMfsDialog(self, dlg):
        self.busy(True)

        await runDialogAsync(dlg)
        if dlg.result() == 0:
            self.busy(False)
            return None

        self.busy(False)
        return dlg.options()

    def _createMfsOptionsDialog(self, type='file'):
        mfsDlg = MFSImportOptionsDialog()
        mfsDlg.ui.filestore.setChecked(self.useFileStore)
        mfsDlg.ui.tsMetadata.setChecked(
            self.timeFrameSelector.useTimeMetadata)
        mfsDlg.ui.rawLeaves.setChecked(self.useRawLeaves)

        if type == 'file':
            mfsDlg.ui.hiddenFiles.setEnabled(False)
            mfsDlg.ui.gitignore.setEnabled(False)
            mfsDlg.ui.wrap.setChecked(
                self.app.settingsMgr.isTrue(
                    CFG_SECTION_UI, CFG_KEY_WRAPSINGLEFILES)
            )
        elif type == 'dir':
            mfsDlg.ui.wrap.setChecked(
                self.app.settingsMgr.isTrue(
                    CFG_SECTION_UI, CFG_KEY_WRAPDIRECTORIES)
            )
        return mfsDlg

    async def onDirsSelected(self, dialog, dirs):
        self.dialogLastDirSelected = dialog.directory()

        if isinstance(dirs, list):
            dir = Path(dirs.pop())
            gitign = dir.joinpath('.gitignore')

            mfsDlg = self._createMfsOptionsDialog(type='dir')
            mfsDlg.ui.gitignore.setChecked(gitign.exists())

            options = await self.runMfsDialog(mfsDlg)

            if options:
                await self.scheduleAddDirectory(str(dir), options)

    def statusAdded(self, name):
        self.statusSet(iAddedFile(name))

    def statusLoading(self, name):
        self.statusSet(iLoading(name))

    def statusSet(self, msg):
        self.ui.mfsStatusLabel.setText(msg)

    def statusEmpty(self):
        self.ui.mfsStatusLabel.setText('')

    def onAddFilesClicked(self):
        dialog = QFileDialog(None)
        dialog.setFileMode(QFileDialog.ExistingFiles)

        dialog.filesSelected.connect(
            lambda files: ensure(self.onFilesSelected(dialog, files)))
        dialog.exec_()

    async def onFilesSelected(self, dialog, files):
        self.dialogLastDirSelected = dialog.directory()

        mfsDlg = self._createMfsOptionsDialog()
        options = await self.runMfsDialog(mfsDlg)

        if options:
            await self.scheduleAddFiles(
                files, options, parent=self.displayPath)

    async def scheduleAddFiles(self, path, options, parent=None):
        if self.isBusy:
            return

        if parent is None:
            parent = self.displayPath

        self._importTask = self.app.task(
            self.addFiles, path, options, parent)
        self.ui.cancelButton.show()

    async def scheduleAddDirectory(self, path, options):
        if self.isBusy or self.inEncryptedFolder:
            return

        self._importTask = self.app.task(
            self.addDirectory, path, options)
        self.ui.cancelButton.show()

    async def scheduleUnlink(self, item, cid):
        reply = await questionBoxAsync(
            'Unlink', 'Do you really want to unlink this item ?')
        if reply:
            await self.unlinkFileFromHash(item, cid)

    async def scheduleDelete(self, item, cid):
        reply = await questionBoxAsync(
            'Delete',
            'Do you really want to delete the object with CID: '
            '<b>{}</b> ?'.format(cid)
        )
        if reply:
            await self.deleteFromCID(item, cid)

    def updateTree(self, timeFrameUpdate=False):
        self.app.task(self.listFiles, self.displayPath,
                      parentItem=self.displayedItem, maxdepth=1,
                      timeFrameUpdate=timeFrameUpdate)

    @ipfsOp
    async def updateKeys(self, ipfsop):
        self.ipfsKeys = await ipfsop.keys()

    @ipfsOp
    async def makeDir(self, ipfsop, parent, path):
        await ipfsop.filesMkdir(os.path.join(parent, path))
        self.updateTree()

    @ipfsOp
    async def listFiles(self, ipfsop, path, parentItem, maxdepth=1,
                        autoexpand=False, timeout=20,
                        timeFrameUpdate=False,
                        **kw):
        if self.isBusy:
            return

        self.enableButtons(flag=False)
        self.sortMfsTree(False)
        self.busy()

        async with self.lock:
            await self.listPathWithTimeout(ipfsop, path, parentItem,
                                           maxdepth=maxdepth,
                                           autoexpand=autoexpand,
                                           timeout=timeout,
                                           **kw)

            if timeFrameUpdate:
                await self.applyTimeFrame()

        self.sortMfsTree(True)
        self.enableButtons()
        self.busy(False)

    async def listPathWithTimeout(self, ipfsop, path, parentItem, **kw):
        timeout = kw.pop('timeout', 20)
        try:
            with async_timeout.timeout(timeout):
                await self.listPath(ipfsop, path, parentItem, **kw)
        except asyncio.TimeoutError:
            self.statusSet(iListingMFSTimeout(path))
        except aioipfs.APIError as err:
            self.statusSet(iIpfsError(err.message))
        except Exception:
            import traceback
            traceback.print_exc()

    async def findInParent(self, parentItem, entry):
        for child in parentItem.childrenItems():
            if isinstance(child, MFSTimeFrameItem):
                async for _tfchild in self.findInParent(child, entry):
                    yield _tfchild

            elif isinstance(child, MFSNameItem):
                if child.entry['Name'] == entry['Name']:
                    if entry['Hash'] != child.entry['Hash']:
                        # The parent has a child item with the same
                        # filename but a different cid: this item
                        # was deleted and needs to be purged from the model
                        # to let the new entry show up
                        await modelhelpers.modelDeleteAsync(
                            self.model, child.entry['Hash'],
                            role=self.model.CidRole
                        )
                if child.entry['Hash'] == entry['Hash']:
                    yield child

            await asyncio.sleep(0)

    async def applyTimeFrame(self):
        try:
            for item in self.displayedItem.childrenItems(
                    type=MFSTimeFrameItem):
                if not item.inRange(
                        self.tfDateFrom,
                        self.tfDateTo):
                    log.debug('applyTimeFrame: purging {}'.format(
                        item.text()))
                    await modelhelpers.modelDeleteAsync(
                        self.model, item.text(),
                        role=self.model.TimeFrameRole
                    )

                await asyncio.sleep(0)
        except Exception as err:
            log.debug('applyTimeFrame error: {}'.format(str(err)))

    def mfsMetadataMatch(self, mfsEntryName):
        return self.mfsMetadataRe.match(mfsEntryName)

    async def listPath(self, op, path, parentItem, depth=0, maxdepth=1,
                       subTask=True,
                       autoexpand=False, timeout=20):
        if not parentItem or not parentItem.path:
            return

        listing = await op.filesList(path)
        if not listing:
            return

        try:
            parentItemSibling = self.model.sibling(parentItem.row(), 0,
                                                   parentItem.index())
        except Exception as err:
            log.debug(f'Sibling error: {err}')
            return

        if parentItemSibling.isValid():
            parentItemHash = self.model.getHashFromIdx(parentItemSibling)
        else:
            parentItemHash = None

        modelParent = None

        for entry in listing:
            entryExists = False

            await asyncio.sleep(0)

            eFound = [e async for e in self.findInParent(parentItem, entry)]
            if len(eFound) > 0:
                entryExists = True

            match = self.mfsMetadataMatch(entry['Name'])

            if match:
                try:
                    mdict = match.groupdict()
                    time = int(mdict.get('time'))
                    entryName = mdict.get('name')

                    _dt = datetime.fromtimestamp(time)
                    _date = date(_dt.year, _dt.month, _dt.day)

                    dateText = _dt.strftime('%Y-%m-%d')
                except Exception:
                    continue

                result = parentItem.findChildByName(dateText)
                if result:
                    modelParent = result
                else:
                    modelParent = MFSTimeFrameItem(
                        _date, dateText, icon=getIcon('clock.png'))

                    if modelParent.inRange(
                            self.tfDateFrom,
                            self.tfDateTo):
                        parentItem.appendRow([modelParent, MFSItem('')])
                    else:
                        continue
            else:
                entryName = entry['Name']
                modelParent = parentItem

            if entryExists:
                nItemName = eFound.pop()
            else:
                icon = None
                if entry['Type'] == 1:  # directory
                    icon = self.iconFolder

                cidString = cidConvertBase32(entry['Hash'])
                nItemName = MFSNameItem(entry, entryName, icon, cidString)

                if entry['Type'] == 1:
                    nItemName.mimeDirectory(self.app.mimeDb)
                else:
                    nItemName.mimeFromDb(self.app.mimeDb)

                nItemName.setParentHash(parentItemHash)
                nItemSize = MFSItem(sizeFormat(entry['Size']))
                nItemName.setToolTip(mfsItemInfosMarkup(nItemName))

                if not icon and nItemName.mimeTypeName:
                    # If we have a better icon matching the file's type..

                    mType = MIMEType(nItemName.mimeTypeName)
                    mIcon = getIconFromMimeType(mType, defaultIcon='unknown')

                    if mIcon:
                        nItemName.setIcon(mIcon)

                # Set its path in the MFS
                nItemName.path = os.path.join(parentItem.path, entry['Name'])

                modelParent.appendRow([nItemName, nItemSize])

            if entry['Type'] == 1:  # directory
                if autoexpand is True:
                    self.mfsTree.setExpanded(nItemName.index(), True)

                if maxdepth > depth or maxdepth == 0:
                    # We used to await listPath() here but it sucks
                    # tremendously if you have a dead CID in the MFS which
                    # will make the ls timeout and hang the filemanager.
                    # Instead, use listPathWithTimeout() in another task. The
                    # FM status will be set to ready before potential
                    # subfolders are being listed in background tasks, which
                    # is fine

                    coro = self.listPathWithTimeout(
                        op,
                        nItemName.path,
                        nItemName,
                        maxdepth=maxdepth, depth=depth + 1,
                        timeout=timeout)

                    if subTask is True:
                        ensure(coro)
                    else:
                        # Used for searching (all directories are expanded)
                        await coro

            if isinstance(modelParent, MFSTimeFrameItem):
                if modelParent.isToday() or modelParent.isPast3Days():
                    self.mfsTree.expand(modelParent.index())

        if autoexpand is True:
            self.mfsTree.expand(parentItem.index())

        self.model.refreshed.emit(parentItem)

    @ipfsOp
    async def deleteFromCID(self, ipfsop, item, cid):
        _dir = os.path.dirname(item.path)

        entry = await ipfsop.filesLookupHash(_dir, cid)

        if entry:
            # Delete the entry in the MFS directory
            await ipfsop.filesDelete(_dir,
                                     entry['Name'], recursive=True)

            # Purge the item's cid in the model
            # Purge its parent as well because the parent cid will change
            await modelhelpers.modelDeleteAsync(
                self.model, cid,
                role=self.model.CidRole
            )

            if item.parentHash:
                await modelhelpers.modelDeleteAsync(
                    self.model, item.parentHash,
                    role=self.model.CidRole
                )

            ensure(ipfsop.purge(cid))
            log.debug('{0}: deleted'.format(cid))

            self.updateTree()
        else:
            log.debug('Did not find cid {}'.format(cid))

    @ipfsOp
    async def unlinkFileFromHash(self, op, item, cid):
        _dir = os.path.dirname(item.path)

        listing = await op.filesList(_dir)
        for entry in listing:
            await op.sleep()
            if entry['Hash'] == cid:
                await op.filesDelete(_dir, entry['Name'], recursive=True)
                await modelhelpers.modelDeleteAsync(
                    self.model, cid,
                    role=self.model.CidRole
                )

    @ipfsOp
    async def addFilesSelfEncrypt(self, op, files, parent):
        self.enableButtons(flag=False)
        self.busy(showClip=True)

        async def onEntry(entry):
            self.statusAdded(entry['Name'])

        count = 0

        for file in files:
            await op.sleep()
            root = await op.addFileEncrypted(file)

            if root is None:
                self.statusSet(iFileImportError())
                continue

            base = os.path.basename(file)

            await self.linkEntry(file, root, parent, base)
            count += 1

        self.statusSet(iImportedCount(count))
        self.enableButtons()
        self.busy(False)
        self.showCancel(False)
        self.updateTree()
        return True

    @ipfsOp
    async def daemonFilestoreEnabled(self, ipfsop):
        return await op.daemonConfigGet('Experimental.FilestoreEnabled')

    @ipfsOp
    async def addFiles(self, op, files, options, parent):
        """ Add every file with an optional wrapper directory """

        if self.displayedItem is self.model.itemEncrypted and op.rsaAgent:
            return await self.addFilesSelfEncrypt(files, parent)

        wrapEnabled = options['wrap']

        self.enableButtons(flag=False)
        self.busy(showClip=True)

        async def onEntry(entry):
            self.statusAdded(entry['Name'])

        count = 0
        for file in files:
            await op.sleep()

            root = await op.addPath(
                file,
                wrap=wrapEnabled,
                dagformat=self.dagGenerationFormat,
                rawleaves=options['rawLeaves'],
                chunker=self.chunkingAlg,
                hashfunc=self.hashFunction,
                useFileStore=options['useFilestore'],
                callback=onEntry)

            if root is None:
                self.statusSet(iFileImportError())
                self.showCancel(False)
                continue

            base = os.path.basename(file)
            if wrapEnabled is True:
                base += '.dirw'

            await self.linkEntry(
                file, root, parent,
                basename=base,
                tsMetadata=options['tsMetadata']
            )
            count += 1

        self.statusEmpty()
        self.enableButtons()
        self.showCancel(False)
        self.busy(False)
        self.updateTree()
        return True

    def onCancelOperation(self):
        if self._importTask:
            self._importTask.cancel()
            self.statusSet(iFileImportCancelled())

    @ipfsOp
    async def addDirectory(self, op, path, options):
        wrapEnabled = options['wrap']
        useGitIgn = options['useGitIgnore']

        self.enableButtons(flag=False)
        self.busy(showClip=True)

        basename = os.path.basename(path)

        async def onEntry(entry):
            self.statusAdded(entry['Name'])

        dirEntry = await op.addPath(
            path,
            callback=onEntry,
            hidden=options['hiddenFiles'],
            recursive=True,
            dagformat=self.dagGenerationFormat,
            rawleaves=options['rawLeaves'],
            chunker=self.chunkingAlg,
            hashfunc=self.hashFunction,
            useFileStore=options['useFilestore'],
            ignRulesPath='.gitignore' if useGitIgn else None,
            wrap=wrapEnabled
        )

        if not dirEntry:
            # Nothing went through ?
            self.enableButtons()
            self.showCancel(False)
            self.busy(False)
            return False

        if wrapEnabled is True:
            basename += '.dirw'

        await self.linkEntry(
            path, dirEntry, self.displayPath,
            basename=basename,
            tsMetadata=options['tsMetadata']
        )

        self.enableButtons()
        self.busy(False)
        self.updateTree()
        self.showCancel(False)
        self.statusEmpty()

        return True

    async def linkEntry(self, fpath, entry, dest, tsMetadata=False,
                        basename=None):
        path = Path(fpath)

        if tsMetadata:
            return await self.linkEntryWithMetadata(
                fpath, entry, dest,
                basename=basename if basename else path.name)
        else:
            return await self.linkEntryNoMetadata(
                entry, dest,
                basename=basename if basename else path.name)

    @ipfsOp
    async def linkEntryNoMetadata(self, op, entry, dest, basename):
        for lIndex in range(0, 16):
            await op.sleep()
            if lIndex == 0:
                lNew = basename
            else:
                lNew = '{0}.{1}'.format(basename, lIndex)
            lookup = await op.filesLookup(dest, lNew)
            if not lookup:
                await op.sleep()
                linkS = await op.filesLink(entry, dest, name=lNew)
                if linkS:
                    return lNew

    @ipfsOp
    async def linkEntryWithMetadata(self, ipfsop,
                                    fpath: str,
                                    entry: dict,
                                    mfsDestDir: str,
                                    basename: str):
        path = Path(fpath)

        try:
            stat = path.stat()
            t = int(time.time())
            mtime = int(stat.st_mtime)

            linkName = f'_mfsmeta_{t}_{mtime}_{stat.st_size}_{basename}'
            await ipfsop.filesLink(entry, mfsDestDir, name=linkName)
        except Exception:
            log.debug(f'Cannot link {entry} to {mfsDestDir} in the MFS')


class FileManagerTab(GalacteekTab):
    def __init__(self, gWindow, fileManager=None):
        super(FileManagerTab, self).__init__(gWindow, sticky=True)

        self.fileManager = fileManager if fileManager else \
            FileManager(parent=self)
        self.fileManager.setupModel()

        self.addToLayout(self.fileManager)
