import importlib
from galacteek import ensure

from galacteek import log
from galacteek.core.objects import GObject
from galacteek.ipdapps import availableDapps
from galacteek.ipdapps import dappsPkg
from galacteek.smartcontracts import getContractByName


class DappsRegistry(GObject):
    def __init__(self, ethController, parent=None):
        super().__init__(parent)
        self._dapps = {}
        self.ethCtrl = ethController

    async def loadDappFromAddr(self, dappName, contractName, address):
        lContract = getContractByName(contractName)
        if not lContract:
            return

        def load(_lContract, address):
            # Blocking call ?
            w3Contract = _lContract.web3Contract(self.web3)
            return w3Contract(address)

        contract = await self._e(load, lContract, address)
        if contract:
            return lContract.module.contractOperator(self, contract,
                                                     address, parent=self)
        else:
            log.debug('Contract invalid: {}'.format(address))

    async def loadDapp(self, dappName, **params):
        dapps = availableDapps()
        dappPath = dapps.get(dappName, None)

        if not dappPath:
            return None

        modname = '{0}.{1}'.format(dappsPkg, dappName)

        try:
            module = importlib.import_module(modname)
        except Exception as err:
            print(str(err))
            return None

        if module:
            dapp = module.Dapp(
                self.ethCtrl,
                dappName,
                dappPath,
                initModule=module,
                parent=self,
                **params
            )
            dapp.pkgContentsChanged.connect(self.onDappPkgChanged)
            await dapp.registerSchemeHandlers()
            await dapp.init()
            self._dapps[dappName] = dapp
            return dapp

    def onDappPkgChanged(self, dappName):
        dapp = self._dapps.get(dappName)
        if dapp:
            dapp.pkgContentsChanged.disconnect(self.onDappPkgChanged)
            dapp.reimportModule()
            dapp.stop()
            del self._dapps[dappName]

            ensure(self.loadDapp(dappName))
