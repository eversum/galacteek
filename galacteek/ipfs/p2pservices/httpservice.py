import json
import base64
import traceback

from galacteek.did import normedUtcDate
from galacteek.did import didIdentRe
from galacteek.ipfs.tunnel import P2PListener
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.p2pservices import P2PService
from galacteek.core import jsonSchemaValidate
from galacteek.crypto.rsa import RSAExecutor
from galacteek.ld import asyncjsonld as jsonld
from galacteek import log

from aiohttp import web


class BaseWebHandler:
    def __init__(self, service):
        self.service = service

    def message(self, msg, level='debug'):
        getattr(log, level)(msg)

    @ipfsOp
    async def expand(self, ipfsop, document):
        async with ipfsop.ldOps() as ld:
            return await ld.expandDocument(document)

    async def msgError(self, error='Invalid request', status=500):
        return web.json_response({
            'error': error
        }, status=status)


class BaseWebApplication(web.Application):
    async def initP2PApp(self, **kw):
        pass


class BaseWebView(web.View):
    async def get(self):
        return web.json_response({
            'error': 'Not implemented'
        })


class BaseWebListener(P2PListener):
    async def createServer(self, host='127.0.0.1', portRange=[]):
        for port in portRange:
            try:
                self.app = self.service.setupCtx.get('webapp')

                assert self.app is not None
                await self.app.initP2PApp()

                server = await self.loop.create_server(
                    self.app.make_handler(debug=True), host, port)

                self._server = server
                return (host, port)
            except Exception:
                traceback.print_exc()
                continue


class BaseP2PWebService(P2PService):
    webListenerClass = BaseWebListener

    @ipfsOp
    async def createListener(self, ipfsop):
        self._listener = self.webListenerClass(
            self,
            ipfsop.client,
            self.protocolName,
            self.listenRange,
            None,
            loop=ipfsop.client.loop
        )
        addr = await self.listener.open()
        return addr != None
