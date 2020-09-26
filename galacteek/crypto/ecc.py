import asyncio
import concurrent.futures
import functools

from Cryptodome.PublicKey import ECC


class ECCExecutor(object):
    def __init__(self, loop=None, executor=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.executor = executor if executor else \
            concurrent.futures.ThreadPoolExecutor(max_workers=4)

    async def _exec(self, fn, *args, **kw):
        return await self.loop.run_in_executor(
            self.executor, functools.partial(fn, *args, **kw))

    async def importKey(self, keyData):
        return await self._exec(lambda: ECC.import_key(keyData))

    async def genKeys(self, curve='P-521'):
        def _generateKeypair(size):
            key = ECC.generate(curve=curve)
            privKey = key.export_key(format='PEM')
            pubKey = key.public_key().export_key(format='PEM')
            return privKey, pubKey

        return await self._exec(_generateKeypair, curve)
