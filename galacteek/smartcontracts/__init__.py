import os.path
import pkg_resources
import importlib
import json

from galacteek import log


pkg = __name__


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


class LocalContract:
    def __init__(self, name, rootDir, cPath, modImp, ctype='solidity'):
        self.name = name
        self.rootDir = rootDir
        self.sourcePath = cPath
        self._deployedAddress = None
        self._type = ctype
        self.module = modImp

    def interface(self):
        fp = os.path.join(self.dir, 'interface.json')
        if os.path.exists(fp):
            with open(fp, 'rt') as fd:
                return json.load(fd)

    def compile(self):
        if self.type == 'solidity':
            compiled = solCompileFile(self.sourcePath)
            _id, interface = compiled.popitem()
            return interface
        elif self.type == 'vyper':
            compiled = vyperCompileFile(self.sourcePath)
            return compiled

    def web3Contract(self, w3):
        iface = self.interface()

        if 'bytecode' in iface:
            binary = iface['bytecode']
        elif 'bin' in iface:
            binary = iface['bin']
        else:
            raise ValueError('Invalid interface')

        return w3.eth.contract(
            bytecode=binary,
            abi=iface.get('abi')
        )

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


def listContracts():
    try:
        listing = pkg_resources.resource_listdir(pkg, '')
        for fn in listing:
            contract = getContractByName(fn)
            if contract:
                yield contract
    except Exception:
        pass


def getContractByName(name):
    path = pkg_resources.resource_filename(pkg, name)
    mainSol = os.path.join(path, 'contract.sol')
    vyperPath = os.path.join(path, 'contract.vy')

    if not os.path.isdir(path):
        return None

    modname = '{0}.{1}'.format(pkg, name)

    try:
        module = importlib.import_module(modname)
    except Exception as err:
        print(str(err))
        return None

    if os.path.isfile(mainSol):
        return LocalContract(name, path, mainSol, module, ctype='solidity')
    elif os.path.isfile(vyperPath):
        return LocalContract(name, path, vyperPath, module, ctype='vyper')


def getContractDeployments(name, network='mainnet', autoload=False):
    path = pkg_resources.resource_filename(pkg, name)
    deplPath = os.path.join(path, 'deployments.json')

    if not os.path.isfile(deplPath):
        return []

    try:
        deployments = []
        with open(deplPath, 'rt') as fd:
            jsono = json.load(fd)

        for entry in jsono:
            if entry.get('network') == network:
                if not autoload or autoload == entry.get('autoload'):
                    deployments.append(entry)
        return deployments
    except Exception:
        return []
