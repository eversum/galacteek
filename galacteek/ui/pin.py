import functools

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

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtGui import QBrush
from PyQt5.QtGui import QColor

from galacteek import ensure
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

    def __init__(self, gWindow):
        super(PinStatusWidget, self).__init__(gWindow)

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

    def findPinItems(self, path):
        ret = modelSearch(self.model,
                          search=path, columns=[self.COL_PATH])
        if len(ret) == 0:
            return None

        itemP = self.model.itemFromIndex(ret.pop())

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

    def onCancel(self, qname, path):
        self.removeItem(path)
        self.app.ipfsCtx.pinner.cancel(qname, path)

    def onPinStatusChanged(self, qname, path, statusInfo):
        nodesProcessed = statusInfo['status'].get('Progress', iUnknown())
        items = self.findPinItems(path)

        if not items:
            btnCancel = QToolButton()
            btnCancel.setText(iCancel())
            btnCancel.clicked.connect(lambda: self.onCancel(qname, path))
            btnCancel.setFixedWidth(140)

            itemTs = UneditableItem(str(statusInfo['ts_queued']))
            itemQ = UneditableItem(qname)
            itemP = UneditableItem(path)
            itemStatus = UneditableItem(iPinning())
            itemNodes = UneditableItem(str(nodesProcessed))
            itemC = UneditableItem('')

            self.model.invisibleRootItem().appendRow(
                [itemTs, itemQ, itemP, itemStatus, itemNodes, itemC])
            idx = self.model.indexFromItem(itemC)
            self.tree.setIndexWidget(idx, btnCancel)
        else:
            items['itemProgress'].setText(str(nodesProcessed))

        self.resort()


class PinBatchTab(GalacteekTab):
    pass


class PinBatchWidget(QWidget):
    def __init__(self, basePath, pathList, parent=None):
        super(PinBatchWidget, self).__init__(parent)

        self.basePath = basePath
        self.pathList = pathList

        self.ui = Ui_BatchPinList()
        self.ui.setupUi(self)

        self.ui.labelBasePath.setText(
            'Base IPFS path: <b>{p}</b>'.format(p=str(self.basePath)))

        horizHeader = self.ui.tableWidget.horizontalHeader()
        horizHeader.sectionClicked.connect(self.onHorizSectionClicked)
        horizHeader.setSectionResizeMode(QHeaderView.ResizeToContents)
        self.ui.tableWidget.setHorizontalHeaderLabels(
            [iPath(), iPinSingle(), iPinRecursive()])

        self.ui.tableWidget.verticalHeader().hide()
        self.ui.tableWidget.setRowCount(len(self.pathList))

        self.ui.proceedButton.clicked.connect(self.onPinObjects)
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
            checkBoxS = QCheckBox(self)

            checkBoxR = QCheckBox(self)

            self.ui.tableWidget.setItem(curRow, 0, pItem)
            self.ui.tableWidget.setCellWidget(curRow, 1, checkBoxS)
            self.ui.tableWidget.setCellWidget(curRow, 2, checkBoxR)

            checkBoxS.stateChanged.connect(
                functools.partial(self.pinSingleChecked, pItem.row()))
            checkBoxR.stateChanged.connect(
                functools.partial(self.pinRecursiveChecked, pItem.row()))
            checkBoxS.setCheckState(Qt.Checked)
            added.append(path.objPath)

        self.ui.tableWidget.setRowCount(len(added))

    def onHorizSectionClicked(self, section):
        if section == 1 or section == 2:
            for row in range(self.ui.tableWidget.rowCount()):
                item = self.ui.tableWidget.cellWidget(row, section)
                if item:
                    item.setCheckState(Qt.Checked)

    def pinSingleChecked(self, row, state):
        adjacent = self.ui.tableWidget.cellWidget(row, 2)
        if adjacent and state == Qt.Checked:
            adjacent.setCheckState(Qt.Unchecked)

    def pinRecursiveChecked(self, row, state):
        adjacent = self.ui.tableWidget.cellWidget(row, 1)
        if adjacent and state == Qt.Checked:
            adjacent.setCheckState(Qt.Unchecked)

    def onPinObjects(self):
        self.ui.proceedButton.setText(iPinning() + ' ...')
        self.ui.proceedButton.setEnabled(False)
        ensure(self.pinSelectedObjects())

    @ipfsOp
    async def pinSelectedObjects(self, ipfsop):
        for row in range(self.ui.tableWidget.rowCount()):
            pItem = self.ui.tableWidget.item(row, 0)
            pSingleBox = self.ui.tableWidget.cellWidget(row, 1)
            pRecBox = self.ui.tableWidget.cellWidget(row, 2)

            path = pItem.data(Qt.UserRole)
            if not path:
                await ipfsop.sleep()
                continue

            if pSingleBox.isChecked() or pRecBox.isChecked():
                await ipfsop.ctx.pin(
                    path, recursive=pRecBox.isChecked(),
                    qname='browser-batch')
                pItem.setFlags(Qt.NoItemFlags)
                pSingleBox.setEnabled(False)
                pRecBox.setEnabled(False)

            await ipfsop.sleep(0.2)
