from galacteek.ipfs import ipfsOp


class P2PService:
    def __init__(self, name, description, protocolName, listenRange,
                handler=None, enabled=True, didDefaultRegister=False,
                setupCtx=None):
        self._name = name
        self._description = description
        self._protocolName = protocolName
        self._protocolNameFull = '/x/{0}'.format(protocolName)
        self._listener = None
        self._listenRange = listenRange
        self._enabled = enabled
        self._handler = handler
        self._manager = None
        self._setupCtx = setupCtx if setupCtx else {}
        self._didDefaultRegister = didDefaultRegister

    @property
    def name(self):
        return self._name

    @property
    def setupCtx(self):
        return self._setupCtx

    @property
    def didDefaultRegister(self):
        return self._didDefaultRegister

    @property
    def enabled(self):
        return self._enabled

    @property
    def description(self):
        return self._description

    @property
    def protocolName(self):
        return self._protocolName

    @property
    def protocolNameFull(self):
        return self._protocolNameFull

    @property
    def listener(self):
        return self._listener

    @property
    def listenRange(self):
        return self._listenRange

    @property
    def handler(self):
        return self._handler

    @property
    def manager(self):
        return self._manager

    @manager.setter
    def manager(self, m):
        self._manager = m

    async def start(self):
        if not self.listener:
            await self.createListener()

    async def stop(self):
        if self.listener:
            await self.listener.close()

    @ipfsOp
    async def createListener(self, ipfsop):
        raise Exception('Implement createListener')

    async def serviceStreams(self):
        # Returns streams associated with this service
        return await self.manager.streamsForProtocol(self.protocolNameFull)

    async def serviceStreamsForRemotePeer(self, peerId):
        # Returns streams associated with this service for a peer
        streams = await self.serviceStreams()
        if streams:
            return [s for s in streams if s['RemotePeer'] == peerId]

    async def didServiceInstall(self, ipid):
        pass
