import functools
import time

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QCoreApplication

from PyQt5.QtWidgets import QTreeView
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QAbstractItemView

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtGui import QBrush
from PyQt5.QtGui import QColor

from galacteek import ensure
from galacteek import partialEnsure
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs import ipfsOp
from galacteek.core.modelhelpers import UneditableItem
from galacteek.core.modelhelpers import modelSearch

from .widgets import GalacteekTab

from .ui_batchpinlist import Ui_BatchPinList
from .helpers import messageBox

from .i18n import iPath
from .i18n import iCidOrPath
from .i18n import iUnknown
from .i18n import iPinned
from .i18n import iPinning
from .i18n import iPin
from .i18n import iDoNotPin
from .i18n import iPinSingle
from .i18n import iPinRecursive
from .i18n import iCancel
from .i18n import iInvalidInput


def iQueue():
    return QCoreApplication.translate('PinStatusWidget', 'Queue')


def iStatus():
    return QCoreApplication.translate('PinStatusWidget', 'Status')


def iNodesProcessed():
    return QCoreApplication.translate('PinStatusWidget', 'Nodes')


class PinStatusWidget(GalacteekTab):
    COL_TS = 0
    COL_QUEUE = 1
    COL_PATH = 2
    COL_STATUS = 3
    COL_PROGRESS = 4
    COL_CTRL = 5

    def __init__(self, gWindow, **kw):
        super(PinStatusWidget, self).__init__(gWindow, **kw)

        self.tree = QTreeView()
        self.tree.setObjectName('pinStatusWidget')
        self.boxLayout = QVBoxLayout()
        self.boxLayout.addWidget(self.tree)

        self.ctrlLayout = QHBoxLayout()
        self.btnPin = QPushButton(iPin())
        self.pathLabel = QLabel(iCidOrPath())
        self.pathEdit = QLineEdit()
        self.ctrlLayout.addWidget(self.pathLabel)
        self.ctrlLayout.addWidget(self.pathEdit)
        self.ctrlLayout.addWidget(self.btnPin)
        self.vLayout.addLayout(self.ctrlLayout)
        self.vLayout.addLayout(self.boxLayout)

        self.app.ipfsCtx.pinItemStatusChanged.connect(self.onPinStatusChanged)
        self.app.ipfsCtx.pinFinished.connect(self.onPinFinished)
        self.app.ipfsCtx.pinItemRemoved.connect(self.onItemRemoved)
        self.pathEdit.returnPressed.connect(self.onPathEntered)
        self.btnPin.clicked.connect(self.onPathEntered)

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(
            ['TS', iQueue(), iPath(), iStatus(), iNodesProcessed(), ''])

        self.tree.setSortingEnabled(True)
        self.tree.setModel(self.model)
        self.tree.sortByColumn(self.COL_TS, Qt.DescendingOrder)

        for col in [self.COL_QUEUE, self.COL_PATH, self.COL_PROGRESS]:
            self.tree.header().setSectionResizeMode(
                col, QHeaderView.ResizeToContents)

        self.tree.hideColumn(self.COL_TS)

    def resort(self):
        self.model.sort(self.COL_TS, Qt.DescendingOrder)

    def onPathEntered(self):
        text = self.pathEdit.text()
        self.pathEdit.clear()

        path = IPFSPath(text)
        if path.valid:
            ensure(self.app.ipfsCtx.pinner.queue(
                path.objPath, True, None))
        else:
            messageBox(iInvalidInput())

    def removeItem(self, path):
        modelSearch(self.model,
                    search=path, columns=[self.COL_PATH],
                    delete=True)

    def onItemRemoved(self, qname, path):
        self.removeItem(path)

    def getIndexFromPath(self, path):
        idxList = self.model.match(
            self.model.index(0, self.COL_PATH),
            Qt.DisplayRole,
            path,
            1,
            Qt.MatchFixedString | Qt.MatchWrap
        )
        if len(idxList) > 0:
            return idxList.pop()

    def findPinItems(self, path):
        idx = self.getIndexFromPath(path)

        if not idx:
            return None

        itemP = self.model.itemFromIndex(idx)

        if not itemP:
            return None

        idxQueue = self.model.index(itemP.row(), self.COL_QUEUE,
                                    itemP.index().parent())
        idxProgress = self.model.index(itemP.row(), self.COL_PROGRESS,
                                       itemP.index().parent())
        idxStatus = self.model.index(itemP.row(), self.COL_STATUS,
                                     itemP.index().parent())
        idxC = self.model.index(itemP.row(), self.COL_CTRL,
                                itemP.index().parent())
        cancelButton = self.tree.indexWidget(idxC)

        return {
            'itemPath': itemP,
            'itemQname': self.model.itemFromIndex(idxQueue),
            'itemProgress': self.model.itemFromIndex(idxProgress),
            'itemStatus': self.model.itemFromIndex(idxStatus),
            'cancelButton': cancelButton
        }

    def updatePinStatus(self, path, status, progress):
        idx = self.getIndexFromPath(path)
        if not idx:
            return

        itemPath = self.model.itemFromIndex(idx)
        if itemPath and time.time() - itemPath.lastProgressUpdate < 5:
            return

        itemProgress = self.model.itemFromIndex(
            self.model.index(idx.row(), self.COL_PROGRESS, idx.parent())
        )

        itemStatus = self.model.itemFromIndex(
            self.model.index(idx.row(), self.COL_STATUS, idx.parent())
        )

        itemStatus.setText(status)
        itemProgress.setText(progress)
        itemPath.lastProgressUpdate = time.time()

    def onPinFinished(self, path):
        items = self.findPinItems(path)

        if items:
            items['itemStatus'].setText(iPinned())
            items['itemProgress'].setText('OK')

            color = QBrush(QColor('#c1f0c1'))
            for item in [items['itemQname'],
                         items['itemPath'], items['itemStatus'],
                         items['itemProgress']]:
                item.setBackground(color)

            if items['cancelButton']:
                items['cancelButton'].setEnabled(False)

        self.resort()
        self.purgeFinishedItems()

    def purgeFinishedItems(self):
        maxFinished = 16
        ret = modelSearch(self.model,
                          search=iPinned(),
                          columns=[self.COL_STATUS])

        if len(ret) > maxFinished:
            rows = []
            for idx in ret:
                item = self.model.itemFromIndex(idx)
                if not item:
                    continue
                rows.append(item.row())

            try:
                for row in list(sorted(rows))[int(maxFinished / 2):]:
                    self.model.removeRow(row)
            except:
                pass

    async def onCancel(self, qname, path, *a):
        self.removeItem(path)
        await self.app.ipfsCtx.pinner.cancel(qname, path)

    def onPinStatusChanged(self, qname, path, statusInfo):
        nodesProcessed = statusInfo['status'].get('Progress', iUnknown())

        idx = self.getIndexFromPath(path)

        if not idx:
            # Register it
            btnCancel = QToolButton()
            btnCancel.setText(iCancel())
            btnCancel.clicked.connect(
                partialEnsure(self.onCancel, qname, path))
            btnCancel.setFixedWidth(140)

            itemTs = UneditableItem(str(statusInfo['ts_queued']))
            itemQ = UneditableItem(qname)
            itemP = UneditableItem(path)
            itemP.setToolTip(path)
            itemP.lastProgressUpdate = time.time()

            itemStatus = UneditableItem(iPinning())
            itemProgress = UneditableItem(str(nodesProcessed))

            itemC = UneditableItem('')

            self.model.invisibleRootItem().appendRow(
                [itemTs, itemQ, itemP, itemStatus, itemProgress, itemC])
            idx = self.model.indexFromItem(itemC)
            self.tree.setIndexWidget(idx, btnCancel)
            self.resort()
        else:
            self.updatePinStatus(path, iPinning(), str(nodesProcessed))


class PinBatchTab(GalacteekTab):
    pass


class PinBatchWidget(QWidget):
    COL_PATH = 0
    COL_NOPIN = 1
    COL_SPIN = 2
    COL_RPIN = 3

    def __init__(self, basePath, pathList, parent=None):
        super(PinBatchWidget, self).__init__(parent)

        self.basePath = basePath
        self.pathList = pathList
        self._pinTask = None

        self.ui = Ui_BatchPinList()
        self.ui.setupUi(self)

        self.ui.labelBasePath.setText(
            'Base IPFS path: <b>{p}</b>'.format(p=str(self.basePath)))

        horizHeader = self.ui.tableWidget.horizontalHeader()
        horizHeader.sectionClicked.connect(self.onHorizSectionClicked)
        horizHeader.setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.tableWidget.setHorizontalHeaderLabels(
            [iPath(), iDoNotPin(), iPinSingle(), iPinRecursive()])

        self.ui.tableWidget.verticalHeader().hide()
        self.ui.tableWidget.setRowCount(len(self.pathList))

        self.ui.proceedButton.clicked.connect(self.onPinObjects)
        self.ui.cancelButton.clicked.connect(self.onCancel)
        self.ui.cancelButton.hide()
        self.insertItems()

    def insertItems(self):
        added = []
        for path in self.pathList:
            if path.objPath in added:
                continue

            curRow = len(added)

            if len(path.objPath) > 92:
                text = path.objPath[0:92] + '...'
            else:
                text = path.objPath

            pItem = QTableWidgetItem(text)

            pItem.setData(Qt.UserRole, path.objPath)
            pItem.setToolTip(path.objPath)
            pItem.setFlags(
                Qt.ItemIsSelectable | Qt.ItemIsEnabled)

            checkBoxN = QCheckBox(self)
            checkBoxS = QCheckBox(self)
            checkBoxR = QCheckBox(self)

            self.ui.tableWidget.setItem(curRow, self.COL_PATH, pItem)
            self.ui.tableWidget.setCellWidget(
                curRow, self.COL_NOPIN, checkBoxN)
            self.ui.tableWidget.setCellWidget(curRow, self.COL_SPIN, checkBoxS)
            self.ui.tableWidget.setCellWidget(curRow, self.COL_RPIN, checkBoxR)

            checkBoxN.stateChanged.connect(
                functools.partial(self.noPinChecked, pItem.row()))
            checkBoxS.stateChanged.connect(
                functools.partial(self.pinSingleChecked, pItem.row()))
            checkBoxR.stateChanged.connect(
                functools.partial(self.pinRecursiveChecked, pItem.row()))
            checkBoxS.setCheckState(Qt.Checked)
            added.append(path.objPath)

        self.ui.tableWidget.setRowCount(len(added))

    def onHorizSectionClicked(self, section):
        if section in [self.COL_NOPIN, self.COL_SPIN, self.COL_RPIN]:
            for row in range(self.ui.tableWidget.rowCount()):
                item = self.ui.tableWidget.cellWidget(row, section)
                if item:
                    item.setCheckState(Qt.Checked)

    def disableAdjacent(self, row, col, state):
        adjacent = self.ui.tableWidget.cellWidget(row, col)
        if adjacent and state == Qt.Checked:
            adjacent.setCheckState(Qt.Unchecked)

    def noPinChecked(self, row, state):
        self.disableAdjacent(row, self.COL_SPIN, state)
        self.disableAdjacent(row, self.COL_RPIN, state)

    def pinSingleChecked(self, row, state):
        self.disableAdjacent(row, self.COL_NOPIN, state)
        self.disableAdjacent(row, self.COL_RPIN, state)

    def pinRecursiveChecked(self, row, state):
        self.disableAdjacent(row, self.COL_NOPIN, state)
        self.disableAdjacent(row, self.COL_SPIN, state)

    def onPinObjects(self):
        self.ui.proceedButton.setText(iPinning() + ' ...')
        self.ui.proceedButton.setEnabled(False)
        self._pinTask = ensure(self.pinSelectedObjects(),
                               futcallback=self.onPinFinished)
        self.ui.cancelButton.show()

    def onPinFinished(self, future):
        try:
            self.ui.cancelButton.hide()
            self.ui.proceedButton.setText('Done')
        except:
            pass

    def onCancel(self):
        if self._pinTask:
            self._pinTask.cancel()

        self.parentWidget().close()

    @ipfsOp
    async def pinSelectedObjects(self, ipfsop):
        def disableRow(pItem, *boxes):
            pItem.setFlags(Qt.NoItemFlags)
            [box.setEnabled(False) for box in boxes]

        for row in range(self.ui.tableWidget.rowCount()):
            pItem = self.ui.tableWidget.item(row, self.COL_PATH)
            noPinBox = self.ui.tableWidget.cellWidget(row, self.COL_NOPIN)
            pSingleBox = self.ui.tableWidget.cellWidget(row, self.COL_SPIN)
            pRecBox = self.ui.tableWidget.cellWidget(row, self.COL_RPIN)

            self.ui.tableWidget.scrollToItem(
                pItem, QAbstractItemView.PositionAtCenter)

            path = pItem.data(Qt.UserRole)
            if not path or noPinBox.isChecked():
                await ipfsop.sleep(0.3)
                disableRow(pItem, noPinBox, pSingleBox, pRecBox)
                continue

            if pSingleBox.isChecked() or pRecBox.isChecked():
                await ipfsop.ctx.pin(
                    path, recursive=pRecBox.isChecked(),
                    qname='browser-batch')
                disableRow(pItem, noPinBox, pSingleBox, pRecBox)

            await ipfsop.sleep(0.3)
