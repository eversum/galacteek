import os.path
import json

from galacteek import log


def vyperCompileFile(file_path, formats=['abi', 'bytecode']):
    from vyper import compile_code
    try:
        with open(file_path, 'r') as f:
            source = f.read()

        return compile_code(source, formats)
    except Exception as err:
        log.debug(str(err))


def solCompileFile(file_path):
    from solcx import compile_source
    try:
        with open(file_path, 'r') as f:
            source = f.read()

        return compile_source(source)
    except Exception as err:
        log.debug(str(err))


def contractDeploy(w3, contract_interface):
    try:
        if 'bytecode' in contract_interface:
            binary = contract_interface['bytecode']
        elif 'bin' in contract_interface:
            binary = contract_interface['bin']
        else:
            raise ValueError('Invalid contract interface')

        contract = w3.eth.contract(
            abi=contract_interface['abi'],
            bytecode=binary)

        txHash = contract.constructor().transact()
        address = w3.eth.getTransactionReceipt(txHash)['contractAddress']
        return address
    except Exception:
        log.debug('Failed to deploy contract')
        return None


class LocalContract:
    def __init__(self, name, rootDir, cPath, ctype='solidity'):
        self.name = name
        self.rootDir = rootDir
        self.sourcePath = cPath
        self._deployedAddress = None
        self._type = ctype

    def interface(self):
        fp = os.path.join(self.dir, 'interface.json')
        if os.path.exists(fp):
            with open(fp, 'rt') as fd:
                return json.load(fd)

    @property
    def type(self):
        return self._type

    @property
    def dir(self):
        return self.rootDir

    @property
    def address(self):
        return self._deployedAddress

    @address.setter
    def address(self, addr):
        self._deployedAddress = addr

    def __repr__(self):
        return 'Local contract: {}'.format(self.sourcePath)


class ContractWrapper:
    def __init__(self, ctrl, contract):
        self.ctrl = ctrl
        self.contract = contract

    async def call(self, fn, *args, **kw):
        txhash = fn.transact()
        receipt = self.ctrl.web3.eth.waitForTransactionReceipt(txhash)
        return receipt
