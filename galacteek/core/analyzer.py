import aioipfs

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject

from galacteek import log
from galacteek import ensure

from galacteek.ipfs import ipfsOp

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import getCID
from galacteek.ipfs.cidhelpers import cidDowngrade
from galacteek.ipfs.mimetype import MIMEType
from galacteek.ipfs.mimetype import detectMimeType
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.ipfssearch import objectMetadata

from galacteek.crypto.qrcode import IPFSQrDecoder


class ResourceAnalyzer(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = QApplication.instance()
        self.qrDecoder = IPFSQrDecoder()

    @ipfsOp
    async def __call__(self, ipfsop, pathRef, fetchExtraMetadata=False):
        """
        :param IPFSPath ipfsPath
        """

        if isinstance(pathRef, IPFSPath):
            ipfsPath = pathRef
        elif isinstance(pathRef, str):
            ipfsPath = IPFSPath(pathRef, autoCidConv=True)
        else:
            log.debug('Invalid path: {path}'.format(path=pathRef))
            return None, None

        path = ipfsPath.objPath
        mHashMeta = await self.app.multihashDb.get(path)

        if mHashMeta:
            # Already have metadata for this object
            typeStr = mHashMeta.get('mimetype')
            mimetype = MIMEType(typeStr) if typeStr else None
            statInfo = mHashMeta.get('stat')
            return mimetype, statInfo
        else:
            mimetype = await detectMimeType(path)

            statInfo = await ipfsop.objStat(path)
            if not statInfo or not isinstance(statInfo, dict):
                log.debug('Stat failed for {path}'.format(
                    path=path))
                return mimetype, None

            await ipfsop.sleep()

            # Store retrieved information in the metadata store
            metaMtype = mimetype.type if mimetype and mimetype.valid else None
            await self.app.multihashDb.store(
                path,
                mimetype=metaMtype,
                stat=statInfo
            )

            # Fetch additional metadata in another task

            if fetchExtraMetadata:
                ensure(self.fetchMetadata(path, statInfo))

        if mimetype and mimetype.valid:
            return mimetype, statInfo

        return None, None

    async def fetchMetadata(self, path, stat):
        sInfo = StatInfo(stat)

        cidobj = getCID(sInfo.cid)
        cid = cidDowngrade(cidobj)

        if not cid:
            return

        metadata = await objectMetadata(str(cid))

        if metadata:
            await self.app.multihashDb.store(
                path,
                objmetadata=metadata
            )

    @ipfsOp
    async def decodeQrCodes(self, ipfsop, path):
        try:
            data = await ipfsop.catObject(path)

            if data is None:
                return

            if not self.qrDecoder:
                # No QR decoding support
                return

            # Decode the QR codes in the image if there's any
            return await self.app.loop.run_in_executor(
                self.app.executor, self.qrDecoder.decode, data)
        except aioipfs.APIError:
            pass
