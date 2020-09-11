import aioipfs
import asyncio

from galacteek import log
from galacteek.ipfs.wrappers import *  # noqa
from galacteek.ipfs.multi import multiAddrTcp4


def protocolFormat(proto, ns='x'):
    return '/{ns}/{proto}'.format(ns=ns, proto=proto)


class P2PProtocol(asyncio.Protocol):
    def __init__(self):
        super(P2PProtocol, self).__init__()

        self.exitFuture = asyncio.Future()
        self.eofReceived = False

    def connection_made(self, transport):
        log.debug('Connection made')
        self.transport = transport

    def data_received(self, data):
        log.debug('Data received {}'.format(data))

    def eof_received(self):
        self.eofReceived = True

    def connection_lost(self, exc):
        self.exitFuture.set_result(True)


class P2PListener(object):
    """
    IPFS P2P listener class

    :param client: AsyncIPFS client
    :param str protocol: protocol name
    :param tuple address: address to listen on
    :param factory: protocol factory
    """

    def __init__(
            self,
            service,
            client,
            protocol,
            addressRange,
            factory,
            loop=None):
        self.service = service
        self.client = client
        self._protocolName = protocol
        self._addressRange = addressRange
        self._listenMultiAddr = None
        self._factory = factory
        self._server = None

        self.loop = loop if loop else asyncio.get_event_loop()

    @property
    def server(self):
        return self._server

    @property
    def protocolName(self):
        return self._protocolName

    @property
    def addressRange(self):
        return self._addressRange

    @property
    def listenMultiAddr(self):
        return self._listenMultiAddr

    @listenMultiAddr.setter
    def listenMultiAddr(self, v):
        log.debug('Listening multiaddr {}'.format(v))
        self._listenMultiAddr = v

    @property
    def protocolFactory(self):
        return self._factory

    @ipfsOp
    async def protocol(self, ipfsoperator):
        async with ipfsoperator as ipfsop:
            if await ipfsop.client.agent_version_post0418():
                return protocolFormat(self.protocolName)
            else:
                return self.protocolName

    @ipfsOp
    async def open(self, ipfsoperator):
        async with ipfsoperator as ipfsop:
            post0418 = await ipfsop.client.agent_version_post0418()

            addrSrv = await self.createServer(
                host=self.addressRange[0],
                portRange=self.addressRange[1]
            )

            if addrSrv is None:
                return None

            listenAddress = '/ip4/{addr}/tcp/{port}'.format(
                addr=addrSrv[0],
                port=addrSrv[1]
            )

            try:
                protocol = await self.protocol()

                log.debug(
                    f'P2PListener: closing listener with proto: {protocol}')

                await self.client.p2p.listener_close(protocol)

                addr = await self.client.p2p.listener_open(
                    protocol, listenAddress)
            except aioipfs.APIError as err:
                # P2P not enabled or some other reason
                log.debug(
                    'P2PListener: creating listener failed: {msg}'.format(
                        msg=err.message))
                return None
            else:
                # Verify the multiaddr
                if post0418:  # go-ipfs>=0.4.18 doesn't return listen address
                    lAddr = listenAddress
                else:
                    lAddr = addr.get('Address', None)
                    if lAddr is None:  # wtf
                        return None

                ipAddr, port = multiAddrTcp4(lAddr)

                if ipAddr == addrSrv[0] and port == addrSrv[1]:
                    self.listenMultiAddr = lAddr
                    return self.listenMultiAddr

    async def createServer(self, host='127.0.0.1', portRange=[]):
        for port in portRange:
            log.debug('P2PListener: trying port {0}'.format(port))

            try:
                srv = await self.loop.create_server(self.protocolFactory,
                                                    host, port)
                if srv:
                    self._server = srv
                    return (host, port)
            except BaseException:
                continue
        return None

    async def stop(self):
        await self.close()

    async def close(self):
        protocol = await self.protocol()
        log.debug('P2PListener: closing {0}'.format(protocol))
        await self.client.p2p.listener_close(protocol)

        if self._server:
            self._server.close()
            await self._server.wait_closed()


class P2PTunnelsManager:
    @ipfsOp
    async def getListeners(self, op):
        try:
            listeners = await op.client.p2p.listener_ls(headers=True)
        except aioipfs.APIError:
            return None
        else:
            return listeners['Listeners']

    @ipfsOp
    async def streams(self, op):
        try:
            resp = await op.client.p2p.ls(headers=True)
            return resp['Listeners']
        except aioipfs.APIError as err:
            log.debug('Error listing streams: {}'.format(err.message))
            return None
        except Exception as err:
            log.debug('Error listing streams: {}'.format(str(err)))
            return None

    @ipfsOp
    async def streamsForProtocol(self, op, protocol):
        allStreams = await self.streams()
        if allStreams:
            log.debug('streamsForProtocol: {!r}'.format(allStreams))
            return [stream for stream in allStreams if
                    stream['Protocol'] == protocol]

    @ipfsOp
    async def streamsForListenAddr(self, op, addr):
        allStreams = await self.streams()
        if allStreams:
            log.debug('streamsForListenAddr: {!r}'.format(allStreams))
            return [stream for stream in allStreams if
                    stream['ListenAddress'] == addr]


@ipfsOpFn
async def dial(ipfsop, peer, protocol, address):
    async with ipfsop as op:
        if await op.client.agent_version_post0418():
            proto = protocolFormat(protocol)
        else:
            proto = protocol

        log.debug('Stream dial {0} {1}'.format(peer, proto))
        try:
            resp = await op.client.p2p.dial(proto, address, peer)
        except aioipfs.APIError as err:
            log.debug(err.message)
            return

        if resp:
            maddr = resp.get('Address', None)
            if not maddr:
                return (None, 0)

            ipaddr, port = multiAddrTcp4(maddr)

            if ipaddr is None or port == 0:
                return (None, 0)

            return (ipaddr, port)
        else:
            ipaddr, port = multiAddrTcp4(address)
            return (ipaddr, port)
