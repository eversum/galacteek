import asyncio
import functools

from PyQt5.QtWidgets import QTreeWidgetItem
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QPushButton

from PyQt5.QtCore import QCoreApplication

from galacteek import ensure
from galacteek import log
from galacteek.appsettings import *  # noqa
from galacteek.ipfs import cidhelpers
from galacteek.ipfs.ipfsops import *  # noqa
from galacteek.ipfs import ipfsOp

from galacteek.ipfs.pb import decodeUnixfsDagNode
from galacteek.ipfs.pb import unixfsDtNames
from galacteek.ipfs.pb import UNIXFS_DT_FILE
from galacteek.ipfs.pb import UNIXFS_DT_RAW

from galacteek.ipfs.dag import DAGPortal
from .helpers import *
from .i18n import *
from .widgets import GalacteekTab
from .widgets import PopupToolButton
from .colors import *

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
    def __init__(self, dagPath, *args, **kw):
        super(DAGViewer, self).__init__(*args, **kw)

        self.dagPath = dagPath
        self._buttons = []

        self.dagWidget = QWidget()
        self.addToLayout(self.dagWidget)
        self.ui = ui_dagview.Ui_DagViewForm()
        self.ui.setupUi(self.dagWidget)

        self.configureTree()

        evfilter = IPFSTreeKeyFilter(self.ui.dagTree)
        evfilter.copyHashPressed.connect(self.onCopyItemHash)
        self.ui.dagTree.installEventFilter(evfilter)

        self.ui.dagTree.itemDoubleClicked.connect(self.onItemDoubleClicked)
        self.ui.dagTree.setHeaderLabels([iKey(), iValue(), ''])
        self.ui.dagPath.setText(iDagInfo(self.dagPath))
        self.ui.collapseButton.clicked.connect(self.onCollapseTree)
        self.ui.expandButton.clicked.connect(self.onExpandTree)

        self.rootItem = self.ui.dagTree.invisibleRootItem()
        self.app.task(self.loadDag, self.dagPath, self.rootItem)

    def configureTree(self):
        # Resize section 1 to be slightly wider than the length of
        # a CIDv1 in base32
        cidSize = self.fontMetrics().size(0, 'a' * (59 + 20))
        self.ui.dagTree.header().resizeSection(1, cidSize.width())

    def onCollapseTree(self):
        self.ui.dagTree.collapseAll()

    def onExpandTree(self):
        self.ui.dagTree.expandAll()

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

        await asyncio.sleep(0)

        if isinstance(data, dict):
            if 'data' in data and 'links' in data:
                node = decodeUnixfsDagNode(data['data'])

                if node is None:
                    dictItem = QTreeWidgetItem(item)
                    dictItem.setText(0, iUnknown())
                    return

                dType = node['type']
                dictItem = QTreeWidgetItem(item)
                dictItem.setText(0, iUnixFSNode())
                dictItem.setText(1,
                                 'Type: {type} ({typeh})'.format(
                                     type=dType,
                                     typeh=unixfsDtNames.get(dType, iUnknown())
                                 ))

                if dType in [UNIXFS_DT_FILE, UNIXFS_DT_RAW] and node['data']:
                    buttonSave = QPushButton(self)
                    buttonSave.setMaximumWidth(
                        self.fontMetrics().size(0, 'UNIX').width())

                    buttonSave.setIcon(getIcon('save-file.png'))
                    buttonSave.clicked.connect(functools.partial(
                        self.copyFileData,
                        node['data']
                    ))

                    fileItem = QTreeWidgetItem(dictItem)
                    fileItem.setText(0, 'data')
                    fileItem.setText(1, 'Data size: {size} bytes'.format(
                        size=len(node['data'])))
                    self.ui.dagTree.setItemWidget(fileItem, 2, buttonSave)

                dictItem.setBackground(0, unixfsNodeColor)
                dictItem.setBackground(1, unixfsNodeColor)
                dictItem.setExpanded(True)

                data.pop('data')
                item = dictItem

            for dkey, dval in data.items():
                if dkey == '/':
                    # Merkle-link
                    linkValue = str(dval)
                    if not cidhelpers.cidValid(linkValue):
                        continue

                    path = cidhelpers.IPFSPath(linkValue)
                    button = PopupToolButton(icon=getIcon('ipld.png'),
                                             parent=self)
                    button.setMaximumWidth(
                        self.fontMetrics().size(0, 'IPLD rules').width())
                    actionView = QAction(getIcon('ipld.png'),
                                         "View link's node", self,
                                         triggered=functools.partial(
                                         self.onFollowDAGLink,
                                         linkValue
                    ))
                    actionOpen = QAction(getIcon('open.png'),
                                         "Open object", self,
                                         triggered=lambda: ensure(
                                         self.app.resourceOpener.open(path)
                    ))

                    button.menu.addAction(actionView)
                    button.menu.addSeparator()
                    button.menu.addAction(actionOpen)
                    button.setDefaultAction(actionView)

                    dictItem = QTreeWidgetItem(item)
                    dictItem.setText(0, iMerkleLink())
                    dictItem.setText(1, cidhelpers.cidConvertBase32(linkValue))
                    dictItem.setToolTip(1, cidInfosMarkup(linkValue))
                    self.ui.dagTree.setItemWidget(dictItem, 2, button)

                    dictItem.setBackground(0, dagLinkColor)
                    dictItem.setBackground(1, dagLinkColor)
                    dictItem.setExpanded(True)
                else:
                    dictItem = QTreeWidgetItem(item)
                    dictItem.setText(0, dkey)
                    dictItem.setExpanded(True)

                    if isinstance(dval, str):
                        dictItem.setText(1, dval)
                        dictItem.setToolTip(1, dval)
                    elif isinstance(dval, int):
                        dictItem.setText(1, str(dval))
                        dictItem.setToolTip(1, str(dval))
                    else:
                        await self.displayItem(dval, dictItem)

        elif isinstance(data, list):
            for i in range(0, len(data)):
                listItem = QTreeWidgetItem(item)
                listItem.setText(0, iDagItem(i))
                listItem.setExpanded(True)
                await self.displayItem(data[i], listItem)
        elif isinstance(data, str):
            # Not a UnixFS node, leaf node ?
            rawItem = QTreeWidgetItem(item)
            rawItem.setText(0, 'Leaf node')
            rawItem.setText(1, data[0:128])
            rawItem.setBackground(0, rawLeafColor)
            rawItem.setBackground(1, rawLeafColor)

    def copyFileData(self, data):
        path = saveFileSelect()

        if path:
            with open(path, 'w+b') as fd:
                fd.write(data)

    def onFollowDAGLink(self, cidString):
        if not cidString:
            return messageBox(iInvalidCID())

        view = DAGViewer(cidhelpers.joinIpfs(cidString), self.app.mainWindow)
        self.app.mainWindow.registerTab(
            view, iDagViewer(),
            current=True,
            icon=getIcon('ipld.png'),
            tooltip=cidString
        )


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
