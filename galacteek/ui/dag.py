import asyncio

from PyQt5.QtWidgets import QTreeWidgetItem
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtGui import QColor

from galacteek import ensure
from galacteek import log
from galacteek.appsettings import *  # noqa
from galacteek.ipfs import cidhelpers
from galacteek.ipfs.ipfsops import *  # noqa
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.dag import DAGPortal
from .helpers import *
from .i18n import *
from .widgets import GalacteekTab

from . import ui_dagview


def iDagError(path):
    return QCoreApplication.translate(
        'DagViewForm', 'Error loading the DAG object: {0}').format(path)


def iDagInfo(obj):
    return QCoreApplication.translate('DagViewForm',
                                      'DAG object: <b>{0}</b>').format(obj)


def iDagItem(it):
    return QCoreApplication.translate('DagViewForm',
                                      'Item {0}').format(it)


class DAGViewer(GalacteekTab):
    def __init__(self, dagHash, *args, **kw):
        super(DAGViewer, self).__init__(*args, **kw)

        self.dagHash = dagHash

        self.dagWidget = QWidget()
        self.addToLayout(self.dagWidget)
        self.ui = ui_dagview.Ui_DagViewForm()
        self.ui.setupUi(self.dagWidget)
        self.mLinkColor = QColor(212, 184, 116)

        evfilter = IPFSTreeKeyFilter(self.ui.dagTree)
        evfilter.copyHashPressed.connect(self.onCopyItemHash)
        self.ui.dagTree.installEventFilter(evfilter)

        self.ui.dagTree.itemDoubleClicked.connect(self.onItemDoubleClicked)
        self.ui.dagTree.setHeaderLabels([iKey(), iValue()])
        self.ui.dagHash.setText(iDagInfo(self.dagHash))

        self.rootItem = self.ui.dagTree.invisibleRootItem()
        self.app.task(self.loadDag, self.dagHash, self.rootItem)

    def onCopyItemHash(self):
        currentItem = self.ui.dagTree.currentItem()
        value = currentItem.text(1)
        if cidhelpers.cidValid(value):
            self.app.setClipboardText(value)

    def onItemDoubleClicked(self, item, col):
        if col == 1:
            text = item.text(col)
            path = cidhelpers.IPFSPath(text)
            if path.valid:
                ensure(self.app.resourceOpener.open(path))

    @ipfsOp
    async def loadDag(self, ipfsop, hashRef, item=None):
        if item is None:
            item = self.rootItem
        await asyncio.sleep(0)
        dagNode = await ipfsop.dagGet(hashRef)
        if not dagNode:
            return messageBox(iDagError(hashRef))

        await self.displayItem(dagNode, item)
        item.setExpanded(True)
        self.ui.dagTree.resizeColumnToContents(0)

    async def displayItem(self, data, item):
        if data is None:
            return
        if isinstance(data, dict):
            for dkey, dval in data.items():
                if dkey == '/':
                    # Merkle-link
                    linkValue = str(dval)
                    if not cidhelpers.cidValid(linkValue):
                        continue

                    dictItem = QTreeWidgetItem(item)
                    dictItem.setText(0, iMerkleLink())
                    dictItem.setText(1, cidhelpers.cidConvertBase32(linkValue))
                    dictItem.setBackground(0, self.mLinkColor)
                    dictItem.setBackground(1, self.mLinkColor)
                    dictItem.setExpanded(True)
                else:
                    dictItem = QTreeWidgetItem(item)
                    dictItem.setText(0, dkey)
                    dictItem.setExpanded(True)
                    if isinstance(dval, str):
                        dictItem.setText(1, dval)
                    elif isinstance(dval, int):
                        dictItem.setText(1, str(dval))
                    else:
                        await self.displayItem(dval, dictItem)

        elif isinstance(data, list):
            for i in range(0, len(data)):
                listItem = QTreeWidgetItem(item)
                listItem.setText(0, iDagItem(i))
                listItem.setExpanded(True)
                await self.displayItem(data[i], listItem)


class DAGBuildingWidget(QWidget):
    """
    You would inherit this class if you have a widget that's gonna
    build a DAG from scratch or refine an existing DAG
    """

    def __init__(self, dagCid=None, offline=True, parent=None):
        super().__init__(parent)
        self.dagOffline = offline

        self._dagCid = dagCid
        self._dag = None

    @ipfsOp
    async def dagInit(self, ipfsop):
        log.debug('Creating new DAG')
        try:
            # Create empty DAG
            cid = await ipfsop.dagPut({}, offline=self.dagOffline, pin=False)
        except aioipfs.APIError:
            # 911
            log.debug('Cannot create DAG ?')
        else:
            if cidhelpers.cidValid(cid):
                self.dagCid = cid
                self._dag = DAGPortal(self.dagCid)

                await ipfsop.sleep()
                await self.dag.load()
                await self.dag.waitLoaded()
