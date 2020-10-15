from Cryptodome.PublicKey import ECC

from galacteek.crypto import BaseCryptoExec

from nacl.public import Box
from nacl.public import SealedBox
from nacl.public import PrivateKey
from nacl.public import PublicKey
import nacl.utils


class Curve25519(BaseCryptoExec):
    async def genKeys(self):
        def _generateKeypair():
            key = PrivateKey.generate()
            return bytes(key), bytes(key.public_key)

        return await self._exec(_generateKeypair)

    async def encrypt(self, msg: bytes, privKey, pubKey):
        def _box():
            try:
                nonce = nacl.utils.random(Box.NONCE_SIZE)
                box = Box(PrivateKey(privKey), PublicKey(pubKey))
                return box.encrypt(msg, nonce)
            except Exception:
                return

        return await self._exec(_box)

    async def decrypt(self, enc, privKey, pubKey):
        def _dec():
            try:
                box = Box(PrivateKey(privKey), PublicKey(pubKey))
                return box.decrypt(enc)
            except Exception:
                return

        return await self._exec(_dec)

    async def encryptSealed(self, msg: bytes, pubKey):
        def _box():
            try:
                nonce = nacl.utils.random(Box.NONCE_SIZE)
                box = SealedBox(PublicKey(pubKey))
                return box.encrypt(msg, nonce)
            except Exception:
                return

        return await self._exec(_box)

    async def decryptSealed(self, enc, privKey):
        def _dec():
            try:
                box = SealedBox(PrivateKey(privKey))
                return box.decrypt(enc)
            except Exception:
                return

        return await self._exec(_dec)


class ECCExecutor(BaseCryptoExec):
    async def importKey(self, keyData):
        return await self._exec(lambda: ECC.import_key(keyData))

    async def genKeys(self, curve='P-521'):
        def _generateKeypair(size):
            key = ECC.generate(curve=curve)
            privKey = key.export_key(format='PEM')
            pubKey = key.public_key().export_key(format='PEM')
            return privKey, pubKey

        return await self._exec(_generateKeypair, curve)
