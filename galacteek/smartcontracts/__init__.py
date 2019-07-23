
import os.path
import pkg_resources

from galacteek.dweb.ethereum.contract import LocalContract


pkg = 'galacteek.smartcontracts'


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

    if os.path.isdir(path) and os.path.isfile(mainSol):
        return LocalContract(name, path, mainSol, ctype='solidity')
    elif os.path.isdir(path) and os.path.isfile(vyperPath):
        return LocalContract(name, path, vyperPath, ctype='vyper')
