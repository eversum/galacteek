import json
from io import BytesIO

from galacteek.ipfs.wrappers import ipfsOp
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
        self.privKeyPath = privKeyPath

    def debug(self, msg):
        log.debug('RSA Agent: {0}'.format(msg))

    async def encrypt(self, data, pubKey):
        return await self.rsaExec.encryptData(
            data if isinstance(data, BytesIO) else BytesIO(data),
            pubKey
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

    async def __rsaReadPrivateKey(self):
        return await asyncReadFile(self.privKeyPath)
