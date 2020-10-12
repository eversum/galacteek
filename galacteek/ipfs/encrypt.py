import json
import orjson
import base64
from io import BytesIO

from jwcrypto import jwk
from jwcrypto import jws
from jwcrypto import jwt
from jwcrypto.common import json_encode

from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import cidValid
from galacteek.core.asynclib import asyncReadFile
from galacteek import log

import aioipfs


class IpfsRSAAgent:
    """
    IPFS RSA Agent

    :param rsaExecutor: RSA Executor object
    :param pubKeyPem: PEM-encoded public key
    :param privKeyPath: Path to private RSA key
    """

    def __init__(self, rsaExecutor, pubKeyPem, privKeyPath):
        self.rsaExec = rsaExecutor
        self.pubKeyPem = pubKeyPem
        self._pubKeyCidCached = None
        self.privKeyPath = privKeyPath

        self.pubJwk = jwk.JWK()
        self.pubJwk.import_from_pem(self.pubKeyPem)

    def debug(self, msg):
        log.debug('RSA Agent: {0}'.format(msg))

    @property
    def pubKeyCidCached(self):
        return self._pubKeyCidCached

    @ipfsOp
    async def pubKeyCid(self, ipfsop):
        if self.pubKeyCidCached and cidValid(self.pubKeyCidCached):
            return self.pubKeyCidCached

        try:
            entry = await ipfsop.addBytes(self.pubKeyPem)
            self._pubKeyCidCached = entry['Hash']
            return self.pubKeyCidCached
        except Exception as err:
            self.debug(f'Cannot import pubkey: {err}')

    async def privJwk(self):
        try:
            privKey = await self.rsaExec.importKey(
                await self.__rsaReadPrivateKey())
            pem = privKey.export_key(pkcs=8)
            key = jwk.JWK()
            key.import_from_pem(pem)
            return key
        except Exception as err:
            self.debug(f'Cannot create priv JWK key: {err}')
            return None

    async def jwsToken(self, payload: str):
        try:
            jwk = await self.privJwk()
            token = jws.JWS(payload.encode('utf-8'))
            token.add_signature(jwk, None,
                                json_encode({"alg": "RS256"}),
                                json_encode({"kid": jwk.thumbprint()}))
            return token
        except Exception as err:
            self.debug(f'Cannot create JWS token: {err}')

    async def jwsTokenObj(self, payload: str):
        token = await self.jwsToken(payload)
        if token:
            return orjson.loads(token.serialize())

    async def jwtCreate(self, claims, alg='RS256'):
        try:
            jwk = await self.privJwk()
            token = jwt.JWT(header={"alg": alg},
                            claims=claims)
            token.make_signed_token(jwk)
            return token.serialize()
        except Exception as err:
            self.debug(f'Cannot create JWT: {err}')

    async def encrypt(self, data, pubKey, sessionKey=None, cacheKey=False):
        return await self.rsaExec.encryptData(
            data if isinstance(data, BytesIO) else BytesIO(data),
            pubKey, sessionKey=sessionKey,
            cacheKey=cacheKey
        )

    async def decrypt(self, data):
        return await self.rsaExec.decryptData(BytesIO(data),
                                              await self.__rsaReadPrivateKey())

    @ipfsOp
    async def storeSelf(self, op, data, offline=False, wrap=False):
        """
        Encrypt some data with our pubkey and store it in IPFS

        Returns the IPFS entry (returned by 'add') of the file

        :param bytes data: data to encrypt
        :param bool offline: offline mode (no announce)

        :rtype: dict
        """
        try:
            encrypted = await self.encrypt(data, self.pubKeyPem)
            if encrypted is None:
                return

            entry = await op.addBytes(encrypted,
                                      offline=offline,
                                      wrap=wrap)
            if entry:
                self.debug(
                    'storeSelf: encoded to {0}'.format(entry['Hash'])
                )
                return entry
        except aioipfs.APIError as err:
            self.debug('IPFS error {}'.format(err.message))

    @ipfsOp
    async def encryptToMfs(self, op, data, mfsPath):
        try:
            encrypted = await self.encrypt(data, self.pubKeyPem)
            if not encrypted:
                return False
            return await op.filesWrite(mfsPath, encrypted,
                                       create=True, truncate=True)
        except aioipfs.APIError as err:
            self.debug('IPFS error {}'.format(err.message))

    @ipfsOp
    async def encryptJsonToMfs(self, op, obj, mfsPath):
        try:
            return await self.encryptToMfs(
                orjson.dumps(obj), mfsPath
            )
        except aioipfs.APIError as err:
            self.debug('IPFS error {}'.format(err.message))

    @ipfsOp
    async def decryptIpfsObject(self, op, data):
        privKey = await self.__rsaReadPrivateKey()
        try:
            decrypted = await self.rsaExec.decryptData(BytesIO(data), privKey)
            if decrypted:
                self.debug('RSA: decrypted {0} bytes'.format(
                    len(decrypted)))
                return decrypted
        except aioipfs.APIError as err:
            self.debug('decryptIpfsObject: IPFS error {}'.format(err.message))
        except Exception as e:
            self.debug('RSA: unknown error while decrypting {}'.format(str(e)))

    @ipfsOp
    async def decryptMfsFile(self, op, path):
        try:
            data = await op.client.files.read(path)
            if data is None:
                raise ValueError('Invalid file')
        except aioipfs.APIError as err:
            self.debug('decryptMfsFile failed for {0}, '
                       'IPFS error was {1}'.format(path, err.message))
        else:
            return await self.decryptIpfsObject(data)

    @ipfsOp
    async def decryptMfsJson(self, op, path):
        try:
            decrypted = await self.decryptMfsFile(path)
            if decrypted:
                return json.loads(decrypted.decode())
        except aioipfs.APIError as err:
            self.debug('decryptMfsJson failed for {0}, '
                       'IPFS error was {1}'.format(path, err.message))

    @ipfsOp
    async def pssSign(self, op, message):
        return await self.rsaExec.pssSign(
            message, await self.__rsaReadPrivateKey())

    @ipfsOp
    async def pssSignImport(self, op, message, pin=False):
        signed = await self.rsaExec.pssSign(
            message, await self.__rsaReadPrivateKey())

        if signed:
            try:
                entry = await op.addBytes(signed, pin=pin)
                return entry['Hash']
            except Exception:
                return None

    @ipfsOp
    async def pssSign64(self, op, message):
        """
        :rtype: str
        """

        signed = await self.pssSign(message)

        if isinstance(signed, bytes):
            return base64.b64encode(signed).decode()

    async def __rsaReadPrivateKeyUtf8(self):
        key = await asyncReadFile(self.privKeyPath, mode='rt')
        return key.encode('utf-8')

    async def __rsaReadPrivateKey(self):
        return await asyncReadFile(self.privKeyPath)
