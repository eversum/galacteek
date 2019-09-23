from datetime import datetime

from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QTreeView
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QFormLayout

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtGui import QBrush
from PyQt5.QtGui import QColor

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QCoreApplication

from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.core.modelhelpers import *

from . import ui_keys, ui_addkeydialog

from .widgets import GalacteekTab
from .helpers import *

from .i18n import iUnknown
from .i18n import iP2PKey


def iKeyName():
    return QCoreApplication.translate('KeysForm', 'Name')


def iKeyResolve():
    return QCoreApplication.translate('KeysForm', 'Resolves to')


class AddKeyDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)

        self.keysView = parent

        self.app = app
        self.ui = ui_addkeydialog.Ui_AddKeyDialog()
        self.ui.setupUi(self)
        self.ui.addKeyLayout.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self.ui.addKeyLayout.setFieldGrowthPolicy(
            QFormLayout.ExpandingFieldsGrow)

    def accept(self):
        keyName = self.ui.keyName.text()
        keySizeText = self.ui.keySize.currentText()

        if len(keyName) == 0:
            return messageBox('Key name is empty')

        self.app.task(self.createKey, keyName, int(keySizeText))

    @ipfsOp
    async def createKey(self, ipfsop, keyName, keySize):
        await ipfsop.client.key.gen(keyName,
                                    type='rsa', size=keySize)
        self.done(1)
        self.keysView.updateKeysList()

    def reject(self):
        self.done(0)


class KeysView(QTreeView):
    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            pass
        QTreeView.mousePressEvent(self, event)


class KeyItem(UneditableItem):
    pass


class KeyResolvedItem(UneditableItem):
    def __init__(self, text):
        super(KeyResolvedItem, self).__init__(text)

        self.resolvedLast = None
        self.resolvesTo = None


class KeysTab(GalacteekTab):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.resolveTimeout = 60 * 5
        self.keysW = QWidget()
        self.addToLayout(self.keysW)
        self.ui = ui_keys.Ui_KeysForm()
        self.ui.setupUi(self.keysW)

        self.ui.addKeyButton.clicked.connect(self.onAddKeyClicked)
        self.ui.deleteKeyButton.clicked.connect(self.onDelKeyClicked)

        self.model = QStandardItemModel(parent=self)

        self.ui.treeKeys = KeysView()
        self.ui.treeKeys.doubleClicked.connect(self.onItemDoubleClicked)
        self.ui.treeKeys.setModel(self.model)

        self.ui.verticalLayout.addWidget(self.ui.treeKeys)

        self.setupModel()
        self.app.task(self.listKeys)

    def setupModel(self):
        self.model.clear()
        self.model.setColumnCount(3)
        self.model.setHorizontalHeaderLabels([
            iKeyName(), iP2PKey(), iKeyResolve()])
        self.ui.treeKeys.header().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.ui.treeKeys.header().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)

    def onDelKeyClicked(self):
        idx = self.ui.treeKeys.currentIndex()
        if not idx.isValid():
            return messageBox('Invalid key')

        idxName = self.model.index(idx.row(), 0, idx.parent())
        keyName = self.model.data(idxName)

        if not keyName:
            return

        reply = questionBox(
            'Delete key', 'Delete IPNS key <b>{key}</b> ?'.format(key=keyName))

        if reply is True:
            self.app.task(self.delKey, keyName)

    def onAddKeyClicked(self):
        runDialog(AddKeyDialog, self.app, parent=self)

    @ipfsOp
    async def delKey(self, ipfsop, name):
        if await ipfsop.keysRemove(name):
            modelDelete(self.model, name)
        self.updateKeysList()

    @ipfsOp
    async def listKeys(self, ipfsop):
        keys = await ipfsop.keys()
        for key in keys:
            found = modelSearch(self.model, search=key['Name'])
            if len(found) > 0:
                continue

            nameItem = UneditableItem(key['Name'])
            nameItem.setToolTip(key['Name'])

            resolveItem = KeyResolvedItem('')
            self.model.appendRow([
                nameItem,
                KeyItem(key['Id']),
                resolveItem
            ])

            self.app.task(self.keyResolve, key, resolveItem)

    @ipfsOp
    async def keyResolve(self, ipfsop, key, item):
        if not isinstance(item, KeyResolvedItem):
            return

        now = datetime.now()

        update = False
        if item.resolvedLast is None:
            update = True

        if isinstance(item.resolvedLast, datetime):
            delta = now - item.resolvedLast
            if delta.seconds > self.resolveTimeout:
                update = True

        if update is True:
            resolved = await ipfsop.nameResolve(key['Id'])

            if isinstance(resolved, dict):
                rPath = resolved.get('Path')
                if not rPath:
                    item.setBackground(QBrush(QColor('red')))
                elif item.resolvesTo and rPath != item.resolvesTo:
                    color = QColor('#c1f0c1')
                    item.setBackground(QBrush(color))
                else:
                    item.setBackground(QBrush(Qt.NoBrush))

                if rPath and IPFSPath(rPath).valid:
                    item.resolvesTo = rPath
                    item.setText(rPath)
                    item.setToolTip(
                        "{path}\n\nResolved date: {date}".format(
                            path=rPath,
                            date=now.isoformat(sep=' ', timespec='seconds')
                        ))
            else:
                item.setText(iUnknown())

            item.resolvedLast = now

        # Ensure another one
        self.app.loop.call_later(
            self.resolveTimeout, self.app.task, self.keyResolve, key, item)

    def updateKeysList(self):
        self.app.task(self.listKeys)

    def onItemDoubleClicked(self, index):
        # Browse IPNS key associated with current item on double-click
        keyHash = self.model.data(self.model.index(index.row(), 1))
        self.gWindow.addBrowserTab().browseIpnsKey(keyHash)
