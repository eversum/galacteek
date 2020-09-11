import json
import base64
import collections
import weakref

from asyncio_throttle import Throttler

from galacteek.did import normedUtcDate
from galacteek.ipfs.tunnel import P2PListener
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.p2pservices import P2PService
from galacteek.ipfs.cidhelpers import ipfsCid32Re
from galacteek.core import jsonSchemaValidate
from galacteek.core.ps import psSubscriber
from galacteek.core.ps import keyTokensDagExchange
from galacteek.crypto.rsa import RSAExecutor
from galacteek import log

from aiohttp import web


pSubscriber = psSubscriber('p2p_dagexchange')


dagCidSignSchema = {
    "title": "DAG CID sign request",
    "type": "object",
    "properties": {
        "cid": {
            "type": "string",
            "pattern": ipfsCid32Re.pattern
        },
        "sessiontoken": {
            "type": "string",
            "pattern": r"[a-f0-9]{64,128}"
        }
    },
    "required": ["cid", "sessiontoken"]
}


class DAGExchangeWebApp(web.Application):
    pass


class DAGExchangeSiteHandler:
    def __init__(self, service):
        self.service = service
        self.throttler = Throttler(
            rate_limit=10,
            period=5.0,
            retry_interval=2.0
        )

    def message(self, msg, level='debug'):
        getattr(log, level)(msg)

    async def msgError(self, error='Invalid request', status=500):
        return web.json_response({
            'error': error
        }, status=status)

    @ipfsOp
    async def dagCidSign(self, ipfsop, request):
        async with self.throttler:
            try:
                js = await request.json()
                if not js or not isinstance(js, dict):
                    return await self.msgError()

                if not jsonSchemaValidate(js, dagCidSignSchema):
                    raise Exception('Invalid req schema')

                cid = js.get('cid')
                token = js.get('sessiontoken')

                if token != self.service._token:
                    raise Exception('Invalid token')

                if not self.service.cidRequestable(cid):
                    log.debug(f'Asked to sign {cid} but not requestable ..')
                    raise Exception('CID not requestable')
            except Exception as err:
                self.message(f'Unauthorized request: {err}')
                return await self.msgError(status=401)

            self.message('Received CID sign request for CID: {}'.format(
                cid))

            try:
                signed = await ipfsop.rsaAgent.pssSign64(cid.encode())

                if signed:
                    return web.json_response({
                        'cid': cid,
                        'pss64': signed
                    })
                else:
                    raise Exception('Cannot sign CID')
            except Exception:
                return await self.msgError()


class DAGExchangeService(P2PService):
    """
    NASDAQ sucks ... What about the ..

    InterPlanetary Signature Service of Directed Acyclic Graphs
    """

    def __init__(self):
        super().__init__(
            'dagexchange',
            'DAG Exchange service',
            'dagexchange',
            ('127.0.0.1', range(49452, 49462)),
            None
        )

        self.__cidQueue = collections.deque([], 10)
        self.__edags = weakref.WeakValueDictionary()

        self._token = None

        pSubscriber.add_async_listener(
            keyTokensDagExchange, self.onDagExchangeToken)

    async def onDagExchangeToken(self, key, message):
        self._token = message['token']
        log.debug(f'Switched service token: {self._token}')

    def queueCid(self, cid):
        self.__cidQueue.appendleft(cid)

    def cidInQueue(self, cid):
        return cid in self.__cidQueue

    def cidRequestable(self, cid: str):
        """
        Checks if we allow to sign a given CID.
        Latest CID and 5 previous CIDs in EDAG history are OK
        """

        for dagMetaPath, edag in self.__edags.items():
            try:
                if edag.dagCid == cid:
                    return True

                dMeta = edag.dagMeta
                if isinstance(dMeta, dict) and 'history' in dMeta:
                    if cid in dMeta['history'][0:5]:
                        return True
            except Exception as err:
                log.debug(f'cidRequestable({cid}): '
                          f'{dagMetaPath}: unknown error: {err}')
                continue

        return False

    def allowEDag(self, edag):
        if edag.dagMetaMfsPath not in self.__edags:
            log.debug(f'Allowing signing for DAG {edag.dagMetaMfsPath}')
            self.__edags[edag.dagMetaMfsPath] = edag

    @ipfsOp
    async def createListener(self, ipfsop):
        self._listener = DAGExchangeListener(
            self,
            ipfsop.client,
            self.protocolName,
            self.listenRange,
            None,
            loop=ipfsop.client.loop
        )
        addr = await self.listener.open()
        log.debug('DAG Exchange service: created listener at address {0}'.format(
            addr))
        return addr != None


class DAGExchangeListener(P2PListener):
    async def createServer(self, host='127.0.0.1', portRange=[]):
        for port in portRange:
            try:
                self.app = DAGExchangeWebApp()
                self.handler = DAGExchangeSiteHandler(self.service)

                self.app.router.add_post('/dagcidsign', self.handler.dagCidSign)

                server = await self.loop.create_server(
                    self.app.make_handler(debug=True), host, port)

                log.debug('DAG Exchange service (port: {port}): started'.format(
                    port=port))

                self._server = server
                return (host, port)
            except Exception:
                continue
