from galacteek.dweb.ethereum.contract import ContractOperator

from galacteek import log


class IpHandlesContractOperator(ContractOperator):
    async def init(self, app):
        pass

    def buildFilter(self, ev='IpHandleAdded', fromBlock=1):
        try:
            ev = getattr(self.contract.events, ev)
            if not ev:
                raise Exception('Event does not exist')

            filter_builder = ev.build_filter()
            filter_builder.fromBlock = fromBlock
            ethFilter = filter_builder.deploy(self.ctrl.web3)
        except Exception as err:
            log.debug(str(err))
        else:
            return ethFilter

    async def vPlanetsList(self):
        vFilter = self.buildFilter(ev='VPlanetAdded')
        all = vFilter.get_all_entries()
        return [log['args']['name'] for log in all]

    async def logsIpHandles(self):
        vFilter = self.buildFilter(ev='IpHandleAdded')
        if vFilter:
            return [log['args'] for log in vFilter.get_all_entries()]

    async def ipHandleExists(self, iphandle: str):
        try:
            return await self.callByName('ipHandleExists', iphandle)
        except Exception:
            return None

    async def registerIpHandle(self, iphandle, did, peerId, proof):
        try:
            result = await self.callTrByName(
                'registerIpHandle',
                iphandle,
                did,
                peerId,
                proof
            )
        except Exception as err:
            log.debug('registerIpHandle error: {}'.format(str(err)))
        else:
            return result

    async def registerVPlanet(self, vPlanet):
        return await self.callTrByName(
            'registerVPlanet',
            vPlanet
        )


contractOperator = IpHandlesContractOperator
