import functools
import asyncio
import concurrent.futures
import async_timeout
import time

from web3 import Web3
from web3.providers.websocket import WebsocketProvider
from web3.auto import w3
from ens import ENS

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal

from galacteek import log
from galacteek import logUser
from galacteek import ensure

from .contract import ContractOperator
from galacteek.smartcontracts import getContractByName

from requests.exceptions import ConnectionError


class EthereumConnectionParams:
    def __init__(self, rpcUrl, provType='http'):
        self.provType = provType
        self.rpcUrl = rpcUrl


class EthBlock:
    def __init__(self, block):
        self._block = block


class DeployedContract:
    def __init__(self, cInterface, address):
        self.interface = cInterface
        self.address = address


class EthereumController(QObject):
    ethConnected = pyqtSignal(bool)
    ethNewBlock = pyqtSignal(str)

    def __init__(self, connParams, web3=None, loop=None,
                 executor=None, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()

        self.loop = loop if loop else asyncio.get_event_loop()
        self.executor = executor if executor else \
            concurrent.futures.ThreadPoolExecutor(max_workers=4)

        self._params = connParams
        self._web3 = web3
        self._watchTask = None
        self._blockLatest = None
        self._stop = False
        self._loadedContracts = {}

    @property
    def web3(self):
        return self._web3

    @property
    def params(self):
        return self._params

    def getWeb3(self):
        try:
            if self._params.provType == 'http':
                web3 = Web3(Web3.HTTPProvider(self.params.rpcUrl))

            elif self._params.provType == 'websocket':
                web3 = Web3(WebsocketProvider(self.params.rpcUrl))
                return web3

            web3.eth.defaultAccount = web3.eth.accounts[0]
            self._ns = ENS.fromWeb3(web3)
            return web3
        except Exception as err:
            log.debug('Cannot get Web3 connector: {}'.format(str(err)))
            return None

    async def _e(self, fn, *args, **kw):
        timeout = kw.pop('timeout', None)
        try:
            if isinstance(timeout, int):
                with async_timeout.timeout(timeout):
                    return await self.loop.run_in_executor(
                        self.executor, functools.partial(fn, *args, **kw))
            else:
                return await self.loop.run_in_executor(
                    self.executor, functools.partial(fn, *args, **kw))
        except asyncio.TimeoutError:
            log.debug('ETH Timeout')
        except ConnectionError:
            log.debug(
                'ETH Connection error while running fn: {0}'.format(fn))
            return None

    # API coroutines

    async def stop(self):
        self._stop = True

    async def start(self):
        if not self._web3:
            self._web3 = self.getWeb3()

        if self.web3 is None:
            log.debug('Web3 invalid')
            return

        if await self.connected():
            logUser.info('Ethereum: connected to {}'.format(
                self.params.rpcUrl))
            self.ethConnected.emit(True)
            # self._watchTask = await self._e(self.watchTask)
            self._watchTask = ensure(self._e(self.watchTask))
            # await self.loadContracts()
        else:
            self.ethConnected.emit(False)

    async def latestBlock(self):
        return await self._e(self.web3.eth.getBlock, 'latest')

    async def getBlock(self, block='latest'):
        return EthBlock(await self._e(self.web3.eth.getBlock, block))

    async def connected(self):
        return await self._e(self.web3.isConnected)

    async def ensAddress(self, name):
        return await self._e(self._ns.address, name)

    def watchTask(self):
        try:
            blkfilter = self.web3.eth.filter('latest')
        except Exception:
            # Node does not support filters ?
            return

        while not self._stop:
            time.sleep(5)

            for event in blkfilter.get_new_entries():
                self.eventLatestBlock(event)

    def eventLatestBlock(self, event):
        if isinstance(event, bytes):
            blockHex = w3.toHex(event)
            self.ethNewBlock.emit(blockHex)

    async def loadContractFromAddress(self, address, abi):
        def load(addr, abi):
            contract = self.web3.eth.contract(
                address=addr,
                abi=abi
            )
            return ContractOperator(self, contract)
        return await self._e(load, address, abi)

    async def loadLocalContractFromAddr(self, contractName, address):
        lContract = getContractByName(contractName)
        if not lContract:
            return

        def load(_lContract, address):
            # Blocking call
            w3Contract = _lContract.web3Contract(self.web3)
            return w3Contract(address)

        contract = await self._e(load, lContract, address)
        if contract:
            operator = lContract.module.contractOperator(self, contract,
                                                         address, parent=self)
            self._loadedContracts.setdefault(contractName, {'default': None})
            self._loadedContracts[contractName][address] = operator

            if self._loadedContracts[contractName]['default'] is None:
                self._loadedContracts[contractName]['default'] = operator

            return lContract, operator
        else:
            log.debug('Contract invalid: {}'.format(address))
            return None, None
