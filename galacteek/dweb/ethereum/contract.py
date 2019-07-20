import os.path
import json

from solcx import compile_source

from galacteek import log


def solCompileFile(file_path):
    try:
        with open(file_path, 'r') as f:
            source = f.read()

        return compile_source(source)
    except Exception as err:
        log.debug(str(err))


def contractDeploy(w3, contract_interface):
    try:
        contract = w3.eth.contract(
            abi=contract_interface['abi'],
            bytecode=contract_interface['bin'])

        txHash = contract.constructor().transact()
        address = w3.eth.getTransactionReceipt(txHash)['contractAddress']
        return address
    except Exception:
        log.debug('Failed to deploy contract')
        return None


class LocalContract:
    def __init__(self, name, rootDir, solPath):
        self.name = name
        self.rootDir = rootDir
        self.solSourcePath = solPath
        self._deployedAddress = None

    def interface(self):
        fp = os.path.join(self.dir, 'interface.json')
        if os.path.exists(fp):
            with open(fp, 'rt') as fd:
                return json.load(fd)

    @property
    def dir(self):
        return self.rootDir

    @property
    def sol(self):
        return self.solSourcePath

    @property
    def address(self):
        return self._deployedAddress

    @address.setter
    def address(self, addr):
        self._deployedAddress = addr

    def __repr__(self):
        return 'Local contract: {}'.format(self.solSourcePath)


class ContractWrapper:
    def __init__(self, ctrl, contract):
        self.ctrl = ctrl
        self.contract = contract

    async def call(self, fn, *args, **kw):
        txhash = fn.transact()
        receipt = self.ctrl.web3.eth.waitForTransactionReceipt(txhash)
        return receipt
