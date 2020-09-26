import asyncio
import concurrent.futures
import functools
import base64

from io import BytesIO

from Cryptodome.Signature import pss
from Cryptodome.PublicKey import RSA
from Cryptodome.Random import get_random_bytes
from Cryptodome.Cipher import AES, PKCS1_OAEP
from Cryptodome.Hash import SHA256

from galacteek import log


class RSAExecutor(object):
    """
    RSA Executor.

    The default executor used is a ThreadPoolExecutor
    """

    def __init__(self, loop=None, executor=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.executor = executor if executor else \
            concurrent.futures.ThreadPoolExecutor(max_workers=4)

    async def _exec(self, fn, *args, **kw):
        return await self.loop.run_in_executor(
            self.executor, functools.partial(fn, *args, **kw))

    async def importKey(self, keyData):
        return await self._exec(lambda: RSA.import_key(keyData))

    async def genKeys(self, keysize=4096):
        """
        Generate RSA keys of the given keysize
        and return a tuple containing the PEM-encoded private and public key
        """
        def _generateKeypair(size):
            key = RSA.generate(size)
            privKey = key.export_key(pkcs=8, protection='scryptAndAES128-CBC')
            pubKey = key.publickey().export_key()
            return privKey, pubKey

        return await self._exec(_generateKeypair, keysize)

    async def encryptData(self, data, recipientKeyData):
        if not isinstance(data, BytesIO):
            raise ValueError('Need BytesIO')
        return await self._exec(self._encryptPkcs1OAEP, data, recipientKeyData)

    def _encryptPkcs1OAEP(self, data, recipientKeyData):
        try:
            recipientKey = RSA.import_key(recipientKeyData)
            sessionKey = get_random_bytes(16)

            cipherRsa = PKCS1_OAEP.new(recipientKey)
            encSessionKey = cipherRsa.encrypt(sessionKey)

            cipherAes = AES.new(sessionKey, AES.MODE_EAX)
            ciphertext, tag = cipherAes.encrypt_and_digest(data.getvalue())

            fd = BytesIO()
            [fd.write(x) for x in (encSessionKey,
                                   cipherAes.nonce, tag, ciphertext)]
            return fd.getvalue()
        except Exception as err:
            log.debug('RSA encryption error {}'.format(str(err)))
            return None

    async def decryptData(self, data, privKey):
        if not isinstance(data, BytesIO):
            raise ValueError('Need BytesIO')
        return await self._exec(self._decryptPkcs1OAEP, data, privKey)

    def _decryptPkcs1OAEP(self, data, privKey):
        if privKey is None:
            raise ValueError('Invalid private key')

        try:
            private = RSA.import_key(privKey)

            encSessionKey, nonce, tag, ciphertext = [
                data.read(x) for x in (
                    private.size_in_bytes(), 16, 16, -1)]

            cipherRsa = PKCS1_OAEP.new(private)
            sessionKey = cipherRsa.decrypt(encSessionKey)

            cipherAes = AES.new(sessionKey, AES.MODE_EAX, nonce)
            data = cipherAes.decrypt_and_verify(ciphertext, tag)

            return data
        except ValueError as verr:
            log.debug('RSA decryption error: {}'.format(str(verr)))
            return None
        except TypeError:
            log.debug('Type error on decryption, check privkey')
            return None

    async def pssSign(self, message: bytes, privRsaKey):
        return await self._exec(self._pssSign, message, privRsaKey)

    def _pssSign(self, message, privRsaKey):
        try:
            key = RSA.import_key(privRsaKey)
            h = SHA256.new(message)
            log.debug('Generating PSS signature')

            signature = pss.new(key).sign(h)

            out = BytesIO()
            out.write(signature)
            return out.getvalue()
        except Exception as err:
            log.debug('Exception on PSS sign: {}'.format(str(err)))
            return None

    async def pssVerif(self, message: bytes, signature: bytes,
                       rsaPubKey):
        return await self._exec(self._pssVerif, message, signature,
                                rsaPubKey)

    async def pssVerif64(self, message: bytes, signature64: bytes,
                         rsaPubKey):
        try:
            decoded = base64.b64decode(signature64)
            return await self._exec(self._pssVerif, message, decoded,
                                    rsaPubKey)
        except Exception as err:
            log.debug(f'Exception on PSS64 verif: {err}')

    def _pssVerif(self, message: bytes, signature, rsaPubKey):
        try:
            key = RSA.import_key(rsaPubKey)
            hashObj = SHA256.new(message)
            verifier = pss.new(key)
            try:
                verifier.verify(hashObj, signature)
                return True
            except (ValueError, TypeError):
                log.debug('The PSS signature is not authentic')
                return False

        except Exception as err:
            log.debug('Exception on PSS verification: {}'.format(str(err)))
            return None
