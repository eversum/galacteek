import asyncio
import concurrent.futures
import functools

from Cryptodome.PublicKey import ECC

from nacl.public import Box
from nacl.public import SealedBox
from nacl.public import PrivateKey
from nacl.public import PublicKey
import nacl.utils


class Curve25519:
    def __init__(self, loop=None, executor=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.executor = executor if executor else \
            concurrent.futures.ThreadPoolExecutor(max_workers=4)

    async def _exec(self, fn, *args, **kw):
        return await self.loop.run_in_executor(
            self.executor, functools.partial(fn, *args, **kw))

    async def genKeys(self):
        def _generateKeypair():
            key = PrivateKey.generate()
            return bytes(key), bytes(key.public_key)

        return await self._exec(_generateKeypair)

    async def encrypt(self, msg: bytes, privKey, pubKey):
        def _box():
            nonce = nacl.utils.random(Box.NONCE_SIZE)
            box = Box(PrivateKey(privKey), PublicKey(pubKey))
            enc = box.encrypt(msg, nonce)
            print('enc', enc)
            return enc

        return await self._exec(_box)

    async def decrypt(self, enc, privKey, pubKey):
        def _dec():
            box = Box(PrivateKey(privKey), PublicKey(pubKey))
            dec = box.decrypt(enc)
            return dec

        return await self._exec(_dec)

    async def encryptSealed(self, msg: bytes, pubKey):
        def _box():
            nonce = nacl.utils.random(Box.NONCE_SIZE)
            box = SealedBox(PublicKey(pubKey))
            enc = box.encrypt(msg, nonce)
            return enc

        return await self._exec(_box)

    async def decryptSealed(self, enc, privKey):
        def _dec():
            box = SealedBox(PrivateKey(privKey))
            dec = box.decrypt(enc)
            return dec

        return await self._exec(_dec)


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
