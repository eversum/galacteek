import re
from pathlib import Path
import asyncio
from dateutil import parser as dateparser
from datetime import datetime

from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QTreeWidgetItem
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QApplication

from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QSpacerItem
from PyQt5.QtWidgets import QToolBar
from PyQt5.QtWidgets import QProgressBar
from PyQt5.QtWidgets import QComboBox

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QSize
from PyQt5.QtCore import pyqtSignal

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtGui import QFont

from galacteek import ensure
from galacteek import ensureLater
from galacteek import partialEnsure
from galacteek import AsyncSignal
from galacteek.database import *
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import *
from galacteek.ipfs.ipfsops import *
from galacteek.ipfs.dag import *
from galacteek.core.modelhelpers import *
from galacteek.database.models.seeds import *


from .clips import RotatingCubeRedFlash140d
from . import ui_seeds
from .widgets import *
from .helpers import *
from .i18n import *


SeedAdded = AsyncSignal(str)
SeedReconfigured = AsyncSignal(str)


class ObjectActionsWidget(QWidget):
    def __init__(self, treeItem, obj, parent=None):
        super().__init__(parent)

        self.sDownload = AsyncSignal()

        self.treeItem = treeItem
        self.obj = obj

        self.hlayout = QHBoxLayout(self)
        self.setLayout(self.hlayout)

        self.btnOpen = QPushButton(iOpen())
        self.btnOpen.setText(iOpen())
        self.btnOpen.setIcon(getIcon('open.png'))
        self.btnOpen.clicked.connect(partialEnsure(self.onOpen))

        self.btnDownload = QToolButton(self)
        self.btnDownload.setText('Download')
        self.btnDownload.clicked.connect(self.onDl)
        self.btnDownload.hide()

        self.hlayout.addWidget(self.btnOpen)
        self.hlayout.addWidget(self.btnDownload)

    def fLayout(self):
        self.hlayout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def onDl(self):
        ensure(self.sDownload.emit())

    def showControls(self, download=False):
        self.btnDownload.setVisible(download)

    async def onOpen(self, *a):
        app = QApplication.instance()
        ensure(app.resourceOpener.open(self.obj['path']))


class StoredSeedObjectActionsWidget(ObjectActionsWidget):
    def __init__(self, treeItem, obj, parent=None):
        super().__init__(treeItem, obj, parent=parent)

        self.sCancel = AsyncSignal()
        self.sRestart = AsyncSignal()

        self.btnCancel = QPushButton(self)
        self.btnCancel.setText('Cancel')
        self.btnCancel.setIcon(getIcon('cancel.png'))
        self.btnCancel.clicked.connect(
            lambda: ensure(self.sCancel.emit()))
        self.btnCancel.hide()

        self.btnRestart = QPushButton(self)
        self.btnRestart.setText('Restart')
        self.btnRestart.clicked.connect(
            lambda: ensure(self.sRestart.emit()))
        self.btnRestart.hide()

        self.hlayout.addWidget(self.btnCancel)
        self.hlayout.addWidget(self.btnRestart)

    def showControls(self, download=False, cancel=False, restart=False):
        self.btnDownload.setVisible(download)
        self.btnCancel.setVisible(cancel)
        self.btnRestart.setVisible(restart)


class StoredSeedActionsWidget(QWidget):
    seedRemove = pyqtSignal()

    def __init__(self, seedingItem, parent=None):
        super().__init__(parent)

        self.seedingItem = seedingItem

        self.hlayout = QHBoxLayout(self)
        self.setLayout(self.hlayout)

        self.btnRemove = QToolButton(self)
        self.btnRemove.setIcon(getIcon('cancel.png'))
        self.btnRemove.clicked.connect(lambda: self.seedRemove.emit())

        self.loadingCube = AnimatedLabel(
            RotatingCubeRedFlash140d(speed=100),
            parent=self
        )
        self.loadingCube.clip.setScaledSize(QSize(24, 24))
        self.loadingCube.hide()

        self.hlayout.addWidget(self.loadingCube)
        self.hlayout.addWidget(self.btnRemove)
        self.hlayout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def busy(self, busy, itemsCount=0):
        if busy:
            self.loadingCube.startClip()
            self.loadingCube.clip.setSpeed(10 * itemsCount)
        else:
            self.loadingCube.stopClip()

        self.loadingCube.setVisible(busy)


seedItemType = Qt.UserRole + 1
seedObjItemType = Qt.UserRole + 2
seedingItemType = Qt.UserRole + 3
seedingObjItemType = Qt.UserRole + 4


class SeedObjectTreeItem(QTreeWidgetItem):
    def __init__(self, seed, objidx, oname, odescr, parent=None):
        super().__init__([oname, 'Init ..'], seedObjItemType)

        self.objidx = objidx
        self.objname = oname
        self.objdescr = odescr
        self.seed = seed

    def _destroy(self):
        pass

    @ipfsOp
    async def update(self, ipfsop):
        oController = ObjectActionsWidget(self, self.objdescr)
        oController.fLayout()
        self.treeWidget().setItemWidget(self, 2, oController)

        self.setData(1, Qt.DisplayRole, 'Searching providers ..')

        whoHas = len(await ipfsop.whoProvides(self.objdescr['path']))
        self.setData(1, Qt.DisplayRole, f'Provided by {whoHas} peers')


class SeedTreeItem(QTreeWidgetItem):
    def __init__(self, seed, *args, type=seedItemType):
        super().__init__(*args, type)
        self.seedDag = seed

    @ipfsOp
    async def loadInfos(self, ipfsop):
        descr = self.seedDag.description

        self.setToolTip(0, descr if descr else self.seedDag.name)

        iconData = await ipfsop.waitFor(self.seedDag.icon(), 1)
        if iconData:
            icon = getIconFromImageData(iconData)
            if icon:
                self.setIcon(0, icon)

    @ipfsOp
    async def lazyLoad(self, ipfsop):
        await self.loadInfos()

        async for oidx, obj in self.seedDag.objects():
            item = SeedObjectTreeItem(
                self.seedDag, oidx, obj['name'], obj)

            self.addChild(item)
            ensure(item.update())

        self.setExpanded(True)


class SeedingObjectTreeItem(QTreeWidgetItem):
    COL_NAME = 0
    COL_FILEINFO = 1
    COL_STATUS = 2
    COL_ACTIONS = 3

    def __init__(self, seed, objidx, oname, odescr, parent=None):
        super().__init__([oname, 'Init ..'], seedingObjItemType)

        self.app = QApplication.instance()
        self.objidx = objidx
        self.objname = oname
        self.objdescr = odescr
        self.seed = seed
        self.stat = None
        self.oController = StoredSeedObjectActionsWidget(self, self.objdescr)
        self.oController.fLayout()
        self.oController.sDownload.connectTo(self.onDownload)
        self.oController.sCancel.connectTo(self.onCancel)
        self.oController.sRestart.connectTo(self.onRestart)
        self._job = None

        self.sJobActive = AsyncSignal(SeedingObjectTreeItem, bool)

    def status(self, text):
        self.setData(self.COL_STATUS, Qt.DisplayRole, text)
        self.setToolTip(self.COL_STATUS, text)

    def fileStatus(self, text):
        self.setData(self.COL_FILEINFO, Qt.DisplayRole, text)
        self.setToolTip(self.COL_FILEINFO, text)

    def _destroy(self):
        pass

    def showActions(self):
        if not self.treeWidget().itemWidget(self, self.COL_ACTIONS):
            self.treeWidget().setItemWidget(
                self, self.COL_ACTIONS, self.oController)

    async def start(self):
        self._job = await self.app.scheduler.spawn(self.watch())
        return self._job

    async def stop(self):
        if self._job:
            await self._job.close()

    async def reconfigure(self):
        await self.stop()
        await self.start()

    def running(self):
        if self._job:
            return self._job.active
        return False

    async def watch(self):
        await self.sJobActive.emit(self, True)

        try:
            await self._watch()
        except asyncio.CancelledError:
            self.treeWidget().setItemWidget(self, self.COL_STATUS, None)
            self.status('Cancelled')
        except Exception:
            pass

        await self.sJobActive.emit(self, False)
        ensureLater(1, self.updateControls)

    @ipfsOp
    async def _watch(self, ipfsop):
        self.status('Analyzing ..')

        stat = await ipfsop.objStat(self.objdescr['path'])
        if not stat:
            self.status('Stat error')
            return
        else:
            self.stat = stat
            self.fileStatus(sizeFormat(stat['CumulativeSize']))

        objConfig = await seedGetObject(self.seed, self.objidx)
        if not objConfig:
            self.status('DB error')
            return

        await self.updateControls(objConfig)

        if objConfig.pin is True:
            if not objConfig.pinned:
                self.status('Pinning')

                prevProg = None
                prevUpdate = None

                async for path, status, progress in ipfsop.pin2(
                        self.objdescr['path']):
                    ltime = self.app.loop.time()

                    if status == 0:
                        if progress:
                            if progress != prevProg:
                                prevProg = progress
                                prevUpdate = ltime

                            diff = int(ltime - prevUpdate)

                            self.status(iPinningProgress(progress, diff))
                        else:
                            self.status(iPinningStalled())
                    elif status == 1:
                        objConfig.pinned = True
                        objConfig.pinnedDate = datetime.now()
                        await objConfig.save()

                        break
                    elif status == -1:
                        self.status('Error')
                        break

                    await ipfsop.sleep(0.05)

            await self.updateControls(objConfig)
            await self.runDownload(objConfig)
        else:
            await self.runDownload(objConfig)

    async def runDownload(self, objConfig):
        if objConfig.download is True:
            if objConfig.downloaded is False:
                dst = await self.downloadObject()
                if dst:
                    objConfig.downloaded = True
                    objConfig.downloadedTo = str(dst)
                    objConfig.downloadedDate = datetime.now()
                    await objConfig.save()

        await self.updateControls(objConfig)

    async def updateControls(self, objConfig=None):
        if not objConfig:
            objConfig = await seedGetObject(self.seed, self.objidx)

        if objConfig.pin:
            if objConfig.pinned:
                self.setIcon(0, getIcon('pin-black.png'))
                self.status(iPinned())

                if objConfig.downloaded is True:
                    self.status(
                        f'Pinned and downloaded to {objConfig.downloadedTo}')
                    objConfig.status = OBJ_STATUS_FINISHED
                    await objConfig.save()
        else:
            if objConfig.downloaded is True:
                self.status(f'Downloaded to {objConfig.downloadedTo}')

                objConfig.status = OBJ_STATUS_FINISHED
                await objConfig.save()

        finished = (objConfig.status == OBJ_STATUS_FINISHED)

        self.showActions()
        self.oController.showControls(
            cancel=not finished and self.running(),
            restart=not finished and not self.running()
        )

    async def onCancel(self):
        await self.stop()

    async def onRestart(self):
        if not self.running():
            await self.start()

    async def onDownload(self):
        objConfig = await seedGetObject(self.seed, self.objidx)
        await self.runDownload(objConfig)

    def baseDownloadDir(self):
        dlPath = Path(self.app.settingsMgr.downloadsPath)

        seedsDir = dlPath.joinpath('seeds')
        baseDir = seedsDir.joinpath(self.seed.name)

        baseDir.mkdir(parents=True, exist_ok=True)
        return baseDir

    @ipfsOp
    async def downloadObject(self, ipfsop):
        pBar = QProgressBar()
        self.treeWidget().setItemWidget(self, 2, pBar)

        baseDir = self.baseDownloadDir()

        try:
            async for result in ipfsop.client.core.getgen(
                    self.objdescr['path'], dstdir=str(baseDir),
                    chunk_size=262144 * 2, sleept=0.1):

                status, read, clength = result

                if status == 0:
                    progress = (read * 100) / clength
                    pBar.setValue(progress)
                elif status == 1:
                    break

                await ipfsop.sleep(0.1)
        except aioipfs.APIError as e:
            self.treeWidget().setItemWidget(self, self.COL_STATUS, None)
            self.status(f'IPFS error: {e.message}')
        except Exception:
            self.treeWidget().setItemWidget(self, self.COL_STATUS, None)
            self.status('Error')
        else:
            pBar.setValue(100)
            self.status('Downloaded')
            self.treeWidget().setItemWidget(self, self.COL_STATUS, None)

            hDir = baseDir.joinpath(self.stat['Hash'])
            nDir = baseDir.joinpath(self.objdescr['name'])

            if nDir.exists():
                return nDir

            if hDir.exists():
                hDir.replace(nDir)
                return nDir


class SeedingTreeItem(SeedTreeItem):
    def __init__(self, seed, *args):
        super().__init__(seed, *args, type=seedingItemType)
        self.app = QApplication.instance()
        self.tasks = []
        self.ctrl = StoredSeedActionsWidget(self)
        self.ctrl.seedRemove.connect(partialEnsure(self.onRemove))

        self.objActiveCount = 0

    def data(self, col, role):
        if role == Qt.UserRole:
            return self.seedDag.dagCid
        else:
            return super().data(col, role)

    async def onRemove(self, *a):
        if await questionBoxAsync('Remove seed', 'Remove seed ?'):
            await self.stop()
            await seedDelete(self.seedDag.dagCid)

            self.treeWidget().invisibleRootItem().removeChild(self)

    async def stop(self):
        for task in self.tasks:
            await task.close()

    def objItems(self):
        for cidx in range(self.childCount()):
            yield self.child(cidx)

    async def reconfigure(self):
        for cidx in range(self.childCount()):
            child = self.child(cidx)
            await child.reconfigure()

    async def onObjJobActive(self, objItem, active):
        if active:
            self.objActiveCount += 1
        else:
            self.objActiveCount -= 1

        self.ctrl.busy(self.objActiveCount > 0, self.objActiveCount)

    @ipfsOp
    async def lazyLoad(self, ipfsop):
        await self.loadInfos()

        async for oidx, obj in self.seedDag.objects():
            item = SeedingObjectTreeItem(
                self.seedDag, oidx, obj['name'], obj, parent=self)

            self.addChild(item)

            item.sJobActive.connectTo(self.onObjJobActive)

            task = await item.start()
            self.tasks.append(task)

        self.treeWidget().setItemWidget(self, 1, self.ctrl)


class SeedActionsWidget(QWidget):
    def __init__(self, treeItem, seed, parent=None):
        super().__init__(parent)

        self.treeItem = treeItem
        self.seedDag = seed

        layout = QHBoxLayout(self)
        self.setLayout(layout)

        icon = getIcon('pin.png')
        combo = QComboBox()
        combo.addItem(icon, iPin())
        combo.addItem(icon, iPinAndDownload())
        combo.addItem(getIcon('download.png'), iDownloadOnly())
        combo.activated.connect(partialEnsure(self.onComboActivated))

        layout.addWidget(combo)
        layout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

    def _destroy(self):
        del self.seedDag
        for ci in range(self.treeItem.childCount()):
            child = self.treeItem.child(ci)
            child._destroy()

    async def onComboActivated(self, idx):
        if idx == 0:
            await self.dbSeed(pin=True, download=False)
        elif idx == 1:
            await self.dbSeed(pin=True, download=True)
        elif idx == 2:
            await self.dbSeed(pin=False, download=True)

    async def onDownload(self, *a):
        await self.dbSeed(pin=False, download=True)

    async def dbSeed(self, pin=True, download=False):
        dbSeed = await seedGet(self.seedDag.dagCid)
        new = False
        if not dbSeed:
            dbSeed = await seedAdd(self.seedDag.dagCid)
            new = True

        async for oidx, obj in self.seedDag.objects():
            await seedConfigObject(dbSeed, oidx, pin=pin, download=download)

        if new:
            await SeedAdded.emit(self.seedDag)
        else:
            await SeedReconfigured.emit(self.seedDag)

        return dbSeed


class TrackerSwitchButton(QToolButton):
    def __init__(self, text, stack, stackidx, allb, parent,
                 checked=False):
        super().__init__(parent)
        self.setText(text)

        self.stack = stack
        self.allButtons = allb
        self.idx = stackidx
        self.setCheckable(True)
        self.setChecked(checked)
        self.clicked.connect(self.onClick)

    def onClick(self):
        self.stack.setCurrentIndex(self.idx)

        for btn in self.allButtons:
            btn.setChecked(False)

        self.setChecked(True)


class SeedsTrackerTab(GalacteekTab):
    COL_ACTIONS = 2

    def __init__(self, gWindow):
        super().__init__(gWindow, sticky=True, vLayout=False)

        self.model = QStandardItemModel(self)

        self.selectedSeed = None

        self.ui = ui_seeds.Ui_Seeds()
        self.ui.setupUi(self)

        SeedAdded.connectTo(self.onSeedAdded)
        SeedReconfigured.connectTo(self.onSeedReconfigured)

        self.sbAll = []
        self.sbSearch = TrackerSwitchButton(
            'Search', self.ui.stack, 0, self.sbAll, self,
            checked=True)
        self.sbPinning = TrackerSwitchButton(
            'In progress', self.ui.stack, 1, self.sbAll, self)
        self.sbAll += [self.sbSearch, self.sbPinning]

        self.resetButton = QPushButton('Reset seeds DB', self)
        self.resetButton.clicked.connect(partialEnsure(self.onSeedsDagReset))

        self.toolbar = QToolBar(self)
        self.toolbar.addWidget(self.sbSearch)
        self.toolbar.addWidget(self.sbPinning)

        self.ui.hLayoutStackControl.addWidget(self.toolbar)
        self.ui.hLayoutStackControl.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.ui.hLayoutStackControl.addWidget(self.resetButton)

        self.searchJob = None
        self.ui.seedsSearch.returnPressed.connect(
            partialEnsure(self.onSearch))

        self.ui.treeAllSeeds.setMouseTracking(True)
        self.ui.treeAllSeeds.setHeaderHidden(True)
        self.ui.treeAllSeeds.setColumnCount(3)
        self.ui.treeAllSeeds.setHeaderLabels(['Name', 'Details', ''])
        self.ui.treeAllSeeds.itemClicked.connect(self.onItemEntered)
        self.ui.treeAllSeeds.currentItemChanged.connect(self.onItemChanged)

        self.ui.treeAllSeeds.header().setDefaultSectionSize(200)
        self.ui.treeAllSeeds.header().resizeSection(0, 300)

        self.ui.treeMySeeds.setMouseTracking(True)
        self.ui.treeMySeeds.setColumnCount(4)
        self.ui.treeMySeeds.setHeaderLabels(['Name', 'Details', ''])

        self.ui.treeMySeeds.header().setDefaultSectionSize(200)
        self.ui.treeMySeeds.header().resizeSection(0, 300)
        self.ui.treeMySeeds.header().resizeSection(1, 100)
        self.ui.treeMySeeds.header().resizeSection(2, 400)
        self.ui.treeMySeeds.header().resizeSection(3, 300)

    @ipfsOp
    async def onSeedsDagReset(self, ipfsop, *a):
        profile = ipfsop.ctx.currentProfile
        seedsDag = profile.dagSeedsAll
        await seedsDag._clear()

    async def onSeedAdded(self, seed):
        root = self.ui.treeMySeeds.invisibleRootItem()
        item = SeedingTreeItem(
            seed, [seed.name]
        )
        ensure(item.lazyLoad())

        root.addChild(item)

    async def onSeedReconfigured(self, seed):
        model = self.ui.treeMySeeds.model()
        idxL = model.match(
            model.index(0, 0, QModelIndex()),
            Qt.UserRole,
            seed.dagCid,
            1,
            Qt.MatchContains | Qt.MatchWrap | Qt.MatchRecursive
        )
        try:
            item = self.ui.treeMySeeds.itemFromIndex(idxL.pop())
            await item.reconfigure()
        except Exception:
            pass

    def onRowsInserted(self, parent, first, last):
        idx = self.model.index(parent, first)
        self.ui.treeAllSeeds.openPersistentEditor(idx)

    def onEntered(self, idx):
        self.ui.treeAllSeeds.openPersistentEditor(idx)

    def changeItem(self, item):
        w = self.ui.treeAllSeeds.itemWidget(item, self.COL_ACTIONS)
        if not w:
            sController = SeedActionsWidget(
                item, item.seedDag, parent=self)
            if item.childCount() == 0:
                ensure(item.lazyLoad())

            self.ui.treeAllSeeds.setItemWidget(
                item, self.COL_ACTIONS, sController)

    def destroySaWidget(self, item):
        w = self.ui.treeAllSeeds.itemWidget(item, self.COL_ACTIONS)
        if w:
            w._destroy()
            self.ui.treeAllSeeds.setItemWidget(item, self.COL_ACTIONS, None)

    def onItemChanged(self, cur, prev):
        if cur and isinstance(cur, SeedTreeItem):
            if self.selectedSeed is not cur:
                self.destroySaWidget(self.selectedSeed)

            self.selectedSeed = cur
            self.changeItem(cur)

    def onItemEntered(self, item, col):
        if col == self.COL_ACTIONS:
            w = self.ui.treeAllSeeds.itemWidget(item, col)
            if not w:
                self.changeItem(item)

    @ipfsOp
    async def onSearch(self, ipfsop):
        if self.searchJob:
            await self.searchJob.close()

        self.ui.treeAllSeeds.clear()
        self.selectedSeed = None
        text = self.ui.seedsSearch.text()

        if text:
            self.searchJob = await self.app.scheduler.spawn(
                self.runSearch(text))

    @ipfsOp
    async def runSearch(self, ipfsop, text):
        try:
            sRegexp = re.compile(text)
        except Exception:
            return await messageBoxAsync(f'Invalid search regexp: {text}')

        self.ui.seedsSearch.setEnabled(False)

        profile = ipfsop.ctx.currentProfile
        seedsDag = profile.dagSeedsAll

        root = self.ui.treeAllSeeds.invisibleRootItem()

        bfont = QFont('Montserrat', 14)
        bfont.setBold(True)
        nfont = QFont('Montserrat', 12)

        try:
            self.ui.treeAllSeeds.setHeaderHidden(False)

            async for result in seedsDag.search(sRegexp):
                section, name, date, dCid = result

                try:
                    dthuman = dateparser.parse(date).isoformat(
                        sep=' ', timespec='seconds')
                except Exception:
                    dthuman = 'No date'

                seed = await ipfsop.waitFor(
                    seedsDag.getSeed(dCid),
                    2
                )

                if not seed:
                    continue

                item = SeedTreeItem(
                    seed,
                    [name, f'{dthuman}', '']
                )
                item.setFont(0, bfont)
                item.setFont(1, nfont)
                item.setFont(2, nfont)

                root.addChild(item)

                selected = self.ui.treeAllSeeds.selectedItems()
                if len(selected) == 0:
                    self.ui.treeAllSeeds.setCurrentItem(item)
                    self.selectedSeed = item

                self.ui.seedsSearch.setEnabled(True)
                await ipfsop.sleep(0.1)
        except asyncio.CancelledError:
            pass

        self.ui.seedsSearch.setEnabled(True)
        self.ui.seedsSearch.setFocus(Qt.OtherFocusReason)

    @ipfsOp
    async def loadSeeds(self, ipfsop):
        profile = ipfsop.ctx.currentProfile
        seedsDag = profile.dagSeedsAll

        storedSeeds = await seedsAll()

        for seed in storedSeeds:
            dag = await seedsDag.getSeed(seed.dagCid)
            await SeedAdded.emit(dag)
