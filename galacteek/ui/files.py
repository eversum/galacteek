import os.path
import asyncio
import functools
import async_timeout

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

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QDir
from PyQt5.QtCore import QSize
from PyQt5.QtCore import pyqtSignal

from galacteek import ensure
from galacteek import GALACTEEK_NAME
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
from galacteek.core.models.mfs import MFSRootItem

from . import ui_files
from . import dag
from .i18n import *  # noqa
from .helpers import *  # noqa
from .widgets import GalacteekTab
from .hashmarks import *  # noqa
from .clipboard import iCopyCIDToClipboard
from .clipboard import iCopyPathToClipboard

import aioipfs

# Files messages


def iFileImportError():
    return QCoreApplication.translate(
        'FileManagerForm', 'Error importing file {}')


def iAddedFile(name):
    return QCoreApplication.translate('FileManagerForm',
                                      'Added {0}').format(name)


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


def iListingMFSTimeout(path):
    return QCoreApplication.translate(
        'FileManagerForm',
        'Timeout while listing MFS path: {0}').format(path)


def iOpenWith():
    return QCoreApplication.translate('FileManagerForm', 'Open with')


def iDeleteFile():
    return QCoreApplication.translate('FileManagerForm', 'Delete file')


def iExploreDir():
    return QCoreApplication.translate('FileManagerForm', 'Explore directory')


def iUnlinkFile():
    return QCoreApplication.translate('FileManagerForm', 'Unlink file')


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


class FileManager(QWidget):
    statusReady = 0
    statusBusy = 1

    displayedItemChanged = pyqtSignal(MFSNameItem)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.clipboard = self.app.appClipboard

        self.lock = asyncio.Lock()
        self.model = None
        self._offlineMode = False

        self.ui = ui_files.Ui_FileManagerForm()
        self.ui.setupUi(self)

        self.status = self.statusReady

        # Build file browser
        self.displayedItem = None
        self.createFileManager()

        self.filesDialog = QFileDialog(None)
        self.dialogLastDirSelected = None

        self.ui.localFileManagerSwitch.setCheckable(True)

        # Connect the various buttons
        self.ui.helpButton.clicked.connect(
            lambda: self.app.manuals.browseManualPage('filemanager.html'))
        self.ui.addFileButton.clicked.connect(self.onAddFilesClicked)
        self.ui.addDirectoryButton.clicked.connect(self.onAddDirClicked)
        self.ui.refreshButton.clicked.connect(self.onRefreshClicked)
        self.ui.searchFiles.returnPressed.connect(self.onSearchFiles)
        self.ui.localFileManagerSwitch.toggled.connect(
            self.onLocalFileManagerToggled)
        self.ui.fileManagerButton.clicked.connect(self.onLocalFileManager)

        # FS options button
        fsOptsMenu = QMenu(self)
        fsDagFormatMenu = QMenu(iDAGGenerationFormat(), self)
        fsDagFormatMenu.setIcon(getIcon('ipld.png'))

        fsMiscOptsMenu = QMenu('Options', self)
        fsMiscOptsMenu.setIcon(getIcon('folder-black.png'))

        self.rawLeavesAction = QAction(
            iRawBlocksForLeaves(), fsMiscOptsMenu)
        self.rawLeavesAction.setCheckable(True)

        fsMiscOptsMenu.addAction(self.rawLeavesAction)

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
        fsOptsMenu.addMenu(fsMiscOptsMenu)

        self.ui.fsOptionsButton.setPopupMode(QToolButton.InstantPopup)
        self.ui.fsOptionsButton.setMenu(fsOptsMenu)

        # Offline mode button
        self.ui.offlineButton.setObjectName('filemanagerOfflineButton')
        self.ui.offlineButton.setText(iOfflineMode())
        self.ui.offlineButton.setCheckable(True)
        self.ui.offlineButton.toggled.connect(self.onOfflineToggle)
        self.ui.offlineButton.setChecked(False)

        # Connect the tree view actions
        self.ui.treeFiles.doubleClicked.connect(self.onDoubleClicked)
        self.ui.treeFiles.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeFiles.customContextMenuRequested.connect(
            self.onContextMenu)
        self.ui.treeFiles.expanded.connect(self.onExpanded)
        self.ui.treeFiles.collapsed.connect(self.onCollapsed)

        self.ui.comboIconSize.addItem('Small')
        self.ui.comboIconSize.addItem('Medium')
        self.ui.comboIconSize.addItem('Large')
        self.ui.comboIconSize.currentIndexChanged.connect(self.onIconSize)

        self.ui.collapseAll.clicked.connect(self.onCollapseAll)
        self.ui.collapseAll.hide()

        # Connect the event filter
        evfilter = IPFSTreeKeyFilter(self.ui.treeFiles)
        evfilter.copyHashPressed.connect(self.onCopyItemHash)
        evfilter.copyPathPressed.connect(self.onCopyItemPath)
        evfilter.returnPressed.connect(self.onReturn)
        evfilter.explorePressed.connect(self.onExploreItem)
        self.ui.treeFiles.installEventFilter(evfilter)

        self.displayedItemChanged.connect(self.onItemChange)

        # Setup the tree view
        self.ui.treeFiles.setExpandsOnDoubleClick(True)
        self.ui.treeFiles.setItemsExpandable(True)
        self.ui.treeFiles.setSortingEnabled(True)
        self.ui.treeFiles.sortByColumn(0, Qt.AscendingOrder)
        self.ui.treeFiles.setIconSize(QSize(16, 16))

        self.iconFolder = getIcon('folder-open.png')
        self.iconFile = getIcon('file.png')

        # Configure drag-and-drop
        self.ui.treeFiles.setAcceptDrops(True)
        self.ui.treeFiles.setDragDropMode(QAbstractItemView.DragDrop)

        self.ipfsKeys = []

    @property
    def gWindow(self):
        return self.app.mainWindow

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
    def displayPath(self):
        if self.displayedItem:
            return self.displayedItem.path

    @property
    def busy(self):
        return self.status == self.statusBusy

    @property
    def rscOpenTryDecrypt(self):
        return self.displayedItem is self.model.itemEncrypted or \
            self.displayedItem is self.model.itemQrCodes

    @property
    def inEncryptedFolder(self):
        return self.displayedItem is self.model.itemEncrypted

    def createFileManager(self):
        self.fManagerModel = QFileSystemModel()
        self.fManagerModel.setRootPath('')

        self.localTree = QTreeView()
        self.localTree.setModel(self.fManagerModel)
        self.localTree.setDragEnabled(True)
        self.localTree.setDragDropMode(QAbstractItemView.DragOnly)
        self.localTree.setSelectionMode(QAbstractItemView.ExtendedSelection)
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

        self.ui.treeFiles.setModel(self.model)
        self.ui.treeFiles.header().setSectionResizeMode(
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
                    self.ui.pathSelector,
                    self.ui.offlineButton,
                    self.ui.searchFiles]:
            btn.setEnabled(flag)

        if self.displayedItem is self.model.itemEncrypted:
            self.ui.addDirectoryButton.setEnabled(False)

    def currentItem(self):
        currentIdx = self.ui.treeFiles.currentIndex()
        if currentIdx.isValid():
            return self.model.getNameItemFromIdx(currentIdx)

    def onDagFormatChanged(self, action):
        print(action)

    def onIconSize(self, index):
        size = None

        if index == 0:
            size = QSize(16, 16)
        elif index == 1:
            size = QSize(24, 24)
        elif index == 2:
            size = QSize(32, 32)
        else:
            return

        self.ui.treeFiles.setIconSize(size)

    def onCollapseAll(self):
        self.ui.treeFiles.collapseAll()

        if self.displayedItem:
            self.displayedItem.expandedItemsCount = 0
            self.collapseButtonUpdate()

    def onOfflineToggle(self, checked):
        if self.displayedItem:
            self.displayedItem.offline = checked

        self.ui.offlineButton.setToolTip(iOfflineModeToolTip())

    def onClose(self):
        if not self.busy:
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
        self.scheduleAddFiles([path])

    def onDropDirectory(self, path):
        self.scheduleAddDirectory(path)

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
        if self.busy:
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

        if self.app.settingsMgr.hideHashes:
            self.ui.treeFiles.hideColumn(2)

    def changeDisplayItem(self, item):
        self.displayedItem = item
        self.ui.treeFiles.setRootIndex(self.displayedItem.index())
        self.updateTree()
        self.ui.treeFiles.expand(self.displayedItem.index())

        if isinstance(item, MFSRootItem):
            self.displayedItemChanged.emit(item)

        if self.app.settingsMgr.hideHashes:
            self.ui.treeFiles.hideColumn(2)

    def onContextMenuVoid(self, point):
        menu = QMenu(self)
        menu.exec(self.ui.treeFiles.mapToGlobal(point))

    def onContextMenu(self, point):
        idx = self.ui.treeFiles.indexAt(point)
        if not idx.isValid():
            return self.onContextMenuVoid(point)

        nameItem = self.model.getNameItemFromIdx(idx)
        dataHash = self.model.getHashFromIdx(idx)
        ipfsPath = nameItem.fullPath
        menu = QMenu(self)

        def explore(cid):
            self.gWindow.explore(cid)

        def hashmark(mPath, name):
            addHashmark(self.app.marksLocal, mPath, name)

        def copyHashToClipboard(itemHash):
            self.clipboard.setText(itemHash)

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
                                             ipfsPath))
        menu.addSeparator()
        menu.addAction(getIconIpfs64(), iDhtProvide(), functools.partial(
            self.onDhtProvide, dataHash, False))
        menu.addAction(getIconIpfs64(), iDhtProvideRecursive(),
                       functools.partial(self.onDhtProvide, dataHash, True))
        menu.addSeparator()

        menu.addAction(getIcon('ipld.png'), iDagView(),
                       functools.partial(self.onDagView, dataHash))
        menu.addSeparator()

        menu.addAction(getIcon('hashmarks.png'),
                       iHashmarkFile(),
                       functools.partial(hashmark, ipfsPath,
                                         nameItem.entry['Name']))
        menu.addAction(getIconIpfs64(),
                       iBrowseFile(),
                       functools.partial(self.browse, ipfsPath))
        menu.addAction(getIcon('open.png'),
                       iOpen(),
                       functools.partial(ensure, self.app.resourceOpener.open(
                           ipfsPath, openingFrom='filemanager',
                           tryDecrypt=self.rscOpenTryDecrypt)))
        if nameItem.isFile():
            menu.addAction(getIcon('text-editor.png'),
                           'Edit',
                           functools.partial(self.editFile,
                                             nameItem.ipfsPath))

        if nameItem.isDir():
            menu.addAction(getIcon('folder-open.png'),
                           iExploreDir(),
                           functools.partial(explore, dataHash))

        def publishToKey(action):
            key = action.data()['key']['Name']
            oHash = action.data()['hash']

            async def publish(op, oHash, keyName):
                await op.publish(joinIpfs(oHash), key=keyName)

            self.app.ipfsTaskOp(publish, oHash, key)

        # Delete/unlink
        menu.addSeparator()
        menu.addAction(iUnlinkFile(), functools.partial(
            self.scheduleUnlink, nameItem, dataHash))
        menu.addAction(iDeleteFile(), functools.partial(
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

        menu.addSeparator()
        menu.addMenu(publishMenu)
        menu.exec(self.ui.treeFiles.mapToGlobal(point))

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

    def editFile(self, ipfsPath):
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

        nameItem = self.model.getNameItemFromIdx(idx)
        item = self.model.itemFromIndex(idx)
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

    def onSearchFiles(self):
        search = self.ui.searchFiles.text()
        self.ui.treeFiles.keyboardSearch(search)

    def onMkDirClicked(self):
        dirName = QInputDialog.getText(self, 'Directory name',
                                       'Directory name')
        if dirName:
            self.app.task(self.makeDir, self.displayedItem.path,
                          dirName[0])

    def onRefreshClicked(self):
        self.updateTree()
        self.ui.treeFiles.setFocus(Qt.OtherFocusReason)

    def onAddDirClicked(self):
        dialog = QFileDialog(None)

        dialog.setFileMode(QFileDialog.DirectoryOnly)
        dialog.filesSelected.connect(
            lambda dirs: self.onDirsSelected(dialog, dirs))

        return dialog.exec_()

    def onDirsSelected(self, dialog, dirs):
        self.dialogLastDirSelected = dialog.directory()

        if isinstance(dirs, list):
            self.scheduleAddDirectory(dirs.pop())

    def statusAdded(self, name):
        self.statusSet(iAddedFile(name))

    def statusLoading(self, name):
        self.statusSet(iLoading(name))

    def statusSet(self, msg):
        self.ui.statusLabel.setText(msg)

    def onAddFilesClicked(self):
        dialog = QFileDialog(None)
        dialog.setFileMode(QFileDialog.ExistingFiles)

        dialog.filesSelected.connect(
            lambda files: self.onFilesSelected(dialog, files))
        dialog.exec_()

    def onFilesSelected(self, dialog, files):
        self.dialogLastDirSelected = dialog.directory()
        self.scheduleAddFiles(files, parent=self.displayPath)

    def scheduleAddFiles(self, path, parent=None):
        if self.busy:
            return

        if parent is None:
            parent = self.displayPath

        return self.app.task(self.addFiles, path, parent)

    def scheduleAddDirectory(self, path):
        if self.busy or self.inEncryptedFolder:
            return

        return self.app.task(self.addDirectory, path)

    def scheduleUnlink(self, item, cid):
        reply = questionBox('Unlink',
                            'Do you really want to unlink this item ?')
        if reply:
            ensure(self.unlinkFileFromHash(item, cid))

    def scheduleDelete(self, item, cid):
        reply = questionBox(
            'Delete',
            'Do you really want to delete: <b>{}</b>'.format(cid)
        )
        if reply:
            ensure(self.deleteFromCID(item, cid))

    def updateTree(self):
        self.app.task(self.listFiles, self.displayPath,
                      parentItem=self.displayedItem, maxdepth=1)

    @ipfsOp
    async def updateKeys(self, ipfsop):
        self.ipfsKeys = await ipfsop.keys()

    @ipfsOp
    async def makeDir(self, ipfsop, parent, path):
        await ipfsop.filesMkdir(os.path.join(parent, path))
        self.updateTree()

    @ipfsOp
    async def listFiles(self, ipfsop, path, parentItem, maxdepth=0,
                        autoexpand=False, timeout=20):
        if self.busy:
            return

        self.enableButtons(flag=False)
        self.status = self.statusBusy

        await self.listPathWithTimeout(ipfsop, path, parentItem,
                                       maxdepth=maxdepth,
                                       autoexpand=autoexpand,
                                       timeout=timeout)

        self.enableButtons()
        self.status = self.statusReady

    async def listPathWithTimeout(self, ipfsop, path, parentItem, **kw):
        timeout = kw.pop('timeout', 10)
        try:
            with async_timeout.timeout(timeout):
                await self.listPath(ipfsop, path, parentItem, **kw)
        except asyncio.TimeoutError:
            self.statusSet(iListingMFSTimeout(path))
        except aioipfs.APIError as err:
            self.statusSet(iIpfsError(err.message))
        except Exception:
            pass

    async def listPath(self, op, path, parentItem, depth=0, maxdepth=1,
                       autoexpand=False, timeout=10):
        if not parentItem or not parentItem.path:
            return

        self.statusSet(iListingMFSPath(path))

        listing = await op.filesList(path)
        if not listing:
            return

        parentItemSibling = self.model.sibling(parentItem.row(), 2,
                                               parentItem.index())
        parentItemHash = self.model.data(parentItemSibling)

        for entry in listing:
            await asyncio.sleep(0)

            found = False
            for child in parentItem.childrenItems():
                if child.entry['Name'] == entry['Name']:
                    if entry['Hash'] != child.entry['Hash']:
                        # The parent has a child item with the same
                        # filename but a different cid: this item
                        # was deleted and needs to be purged from the model
                        # to let the new entry show up
                        await modelhelpers.modelDeleteAsync(
                            self.model, child.entry['Hash'])
                        break
                if child.entry['Hash'] == entry['Hash']:
                    found = True
                    break

            if found:
                continue

            icon = None
            if entry['Type'] == 1:  # directory
                icon = self.iconFolder

            cidString = cidConvertBase32(entry['Hash'])
            nItemName = MFSNameItem(entry, entry['Name'], icon)
            nItemName.mimeFromDb(self.app.mimeDb)
            nItemName.setParentHash(parentItemHash)
            nItemSize = MFSItem(sizeFormat(entry['Size']))
            nItemCID = MFSItem(cidString)
            nItemCID.setToolTip(cidInfosMarkup(cidString))

            if not icon and nItemName.mimeTypeName:
                # If we have a better icon matching the file's type..

                mType = MIMEType(nItemName.mimeTypeName)
                mIcon = getIconFromMimeType(mType, defaultIcon='unknown')

                if mIcon:
                    nItemName.setIcon(mIcon)

            # Set its path in the MFS
            nItemName.path = os.path.join(parentItem.path, entry['Name'])

            nItem = [nItemName, nItemSize, nItemCID]

            parentItem.appendRow(nItem)

            if entry['Type'] == 1:  # directory
                if autoexpand is True:
                    self.ui.treeFiles.setExpanded(nItemName.index(), True)

                if maxdepth > depth:
                    # We used to await listPath() here but it sucks
                    # tremendously if you have a dead CID in the MFS which
                    # will make the ls timeout and hang the filemanager.
                    # Instead, use listPathWithTimeout() in another task. The
                    # FM status will be set to ready before potential
                    # subfolders are being listed in background tasks, which
                    # is fine

                    ensure(self.listPathWithTimeout(
                        op,
                        nItemName.path,
                        nItemName,
                        maxdepth=maxdepth, depth=depth + 1))

        if autoexpand is True:
            self.ui.treeFiles.expand(parentItem.index())

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
            await modelhelpers.modelDeleteAsync(self.model, cid)

            if item.parentHash:
                await modelhelpers.modelDeleteAsync(
                    self.model, item.parentHash)

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
                await modelhelpers.modelDeleteAsync(self.model, cid)

    @ipfsOp
    async def addFilesSelfEncrypt(self, op, files, parent):
        self.enableButtons(flag=False)
        self.status = self.statusBusy

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

            await self.linkEntry(op, root, parent, base)
            count += 1

        self.statusSet(iImportedCount(count))
        self.enableButtons()
        self.status = self.statusReady
        self.updateTree()
        return True

    @ipfsOp
    async def addFiles(self, op, files, parent):
        """ Add every file with an optional wrapper directory """

        if self.displayedItem is self.model.itemEncrypted and op.rsaAgent:
            return await self.addFilesSelfEncrypt(files, parent)

        wrapEnabled = self.app.settingsMgr.isTrue(
            CFG_SECTION_UI, CFG_KEY_WRAPSINGLEFILES)

        self.enableButtons(flag=False)
        self.status = self.statusBusy

        async def onEntry(entry):
            self.statusAdded(entry['Name'])

        count = 0
        for file in files:
            await op.sleep()

            root = await op.addPath(file, wrap=wrapEnabled,
                                    offline=self.offlineMode,
                                    dagformat=self.dagGenerationFormat,
                                    rawleaves=self.useRawLeaves,
                                    callback=onEntry)

            if root is None:
                self.statusSet(iFileImportError())
                continue

            base = os.path.basename(file)
            if wrapEnabled is True:
                base += '.dirw'

            await self.linkEntry(op, root, parent, base)
            count += 1

        self.statusSet(iImportedCount(count))
        self.enableButtons()
        self.status = self.statusReady
        self.updateTree()
        return True

    @ipfsOp
    async def addDirectory(self, op, path):
        wrapEnabled = self.app.settingsMgr.isTrue(
            CFG_SECTION_UI, CFG_KEY_WRAPDIRECTORIES)

        self.enableButtons(flag=False)
        self.status = self.statusBusy
        basename = os.path.basename(path)
        dirEntry = None

        async def onEntry(entry):
            self.statusAdded(entry['Name'])

        dirEntry = await op.addPath(path, callback=onEntry,
                                    hidden=True, recursive=True,
                                    offline=self.offlineMode,
                                    dagformat=self.dagGenerationFormat,
                                    rawleaves=self.useRawLeaves,
                                    wrap=wrapEnabled)

        if not dirEntry:
            # Nothing went through ?
            self.enableButtons()
            return False

        if wrapEnabled is True:
            basename += '.dirw'

        await self.linkEntry(op, dirEntry, self.displayPath, basename)

        self.enableButtons()
        self.status = self.statusReady
        self.updateTree()
        return True

    async def linkEntry(self, op, entry, dest, basename):
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


class FileManagerTab(GalacteekTab):
    def __init__(self, gWindow, fileManager=None):
        super(FileManagerTab, self).__init__(gWindow)

        self.fileManager = fileManager if fileManager else \
            FileManager(parent=self)
        self.fileManager.setupModel()

        self.addToLayout(self.fileManager)
