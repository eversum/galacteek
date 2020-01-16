from galacteek import log


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


class ContractOperator:
    def __init__(self, ctrl, contract, address, parent=None):
        self.ctrl = ctrl
        self.contract = contract
        self.address = address

    async def call(self, fn, *args):
        def _callwrap(func, *args):
            result = func(*args).call()
            return result

        return await self.ctrl._e(_callwrap, fn, *args)

    async def transact(self, fn, *args):
        def _trwrap(func, *args):
            txHash = func(*args).transact()
            receipt = self.ctrl.web3.eth.waitForTransactionReceipt(txHash, 180)
            return receipt

        return await self.ctrl._e(_trwrap, fn, *args)

    async def callByName(self, fnName, *args, **kw):
        fn = getattr(self.contract.functions, fnName)
        if fn:
            return await self.call(fn, *args)

    async def callTrByName(self, fnName, *args, **kw):
        fn = getattr(self.contract.functions, fnName)
        if fn:
            return await self.transact(fn, *args)

    async def script(self, fn, *args, **kw):
        r = await self.ctrl._e(fn, self.ctrl.web3, self.contract, *args, **kw)
        return r
