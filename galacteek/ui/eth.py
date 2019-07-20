from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtCore import pyqtSignal

from galacteek.dweb.page import IPFSPage
from galacteek.dweb.page import DWebView, WebTab
from galacteek.dweb.page import BaseHandler

from .helpers import getIcon
from .i18n import iUnknown


def iEthConnected(rpcUrl, lBlockHash):
    return QCoreApplication.translate(
        'ethereumStatusButton',
        '''Connected to the Ethereum blockchain
           RPC Url: {0}
           Latest block's hash: {1}
           ''').format(rpcUrl, lBlockHash)


def iEthNotConnected():
    return QCoreApplication.translate(
        'ethereumStatusButton',
        'Not connected to any Ethereum node')


def iEthStatus():
    return QCoreApplication.translate(
        'ethereumStatusButton',
        'Ethereum status')


class asyncSlot:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.name = wrapped.__name__

    @pyqtSlot()
    def __get__(self, inst, owner):
        async def wrapper(*args, **kw):
            return await self.wrapped(inst, *args, **kw)


class EthereumHandler(BaseHandler):
    newBlock = pyqtSignal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller


class EthereumWrapperPage(IPFSPage):
    def __init__(self, controller, parent=None):
        super().__init__('ethstatus.html', parent=parent)
        self.controller = controller
        self.handler = EthereumHandler(self.controller, parent=self)
        self.register('ether', self.handler)
        self.pageCtx['controller'] = self.controller


class EthereumStatusButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setEnabled(False)
        self.app = QApplication.instance()
        self.app.ethereum.ethConnected.connect(self.onEthStatus)
        self.app.ethereum.ethNewBlock.connect(self.onNewBlock)

        self.view = DWebView(parent=None)
        self.view.show()
        self.page1 = EthereumWrapperPage(self.app.ethereum, parent=self.view)
        self.view.p = self.page1

        self.statusTab = None
        self.lBlockHash = None

        self.iconEthereum = getIcon('ethereum.png')
        self.setIcon(self.iconEthereum)

    def onToggled(self, checked):
        tabName = iEthStatus()
        if checked:
            if not self.statusTab:
                self.statusTab = WebTab(self.app.mainWindow)
            self.statusTab.attach(self.view)
            self.app.mainWindow.registerTab(self.statusTab, tabName,
                                            current=True)
        elif not checked and self.statusTab:
            tab = self.app.mainWindow.findTabWithName(tabName)
            if tab:
                self.app.mainWindow.removeTabFromWidget(tab)

            self.statusTab = None

    def onEthStatus(self, connected):
        self.setEnabled(connected)
        if connected:
            self.updateToolTip()
        else:
            self.setToolTip(iEthNotConnected())

    def updateToolTip(self):
        self.setToolTip(iEthConnected(
            self.app.ethereum.params.rpcUrl,
            self.lBlockHash if self.lBlockHash else iUnknown()))

    def onNewBlock(self, blockHash):
        self.lBlockHash = blockHash
        self.updateToolTip()
        self.page1.handler.newBlock.emit(blockHash)
