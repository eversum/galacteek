
import os.path
import pkg_resources

from galacteek.dweb.ethereum.contract import LocalContract


pkg = 'galacteek.smartcontracts'


def listContracts():
    try:
        listing = pkg_resources.resource_listdir(pkg, '')
        for fn in listing:
            path = pkg_resources.resource_filename(pkg, fn)
            mainSol = os.path.join(path, 'contract.sol')
            if os.path.isdir(path) and os.path.isfile(mainSol):
                yield LocalContract(fn, path, mainSol)
    except Exception:
        pass


def getContractByName(name):
    path = pkg_resources.resource_filename(pkg, name)
    mainSol = os.path.join(path, 'contract.sol')
    if os.path.isdir(path) and os.path.isfile(mainSol):
        return LocalContract(name, path, mainSol)
