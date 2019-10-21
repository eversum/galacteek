import aioipfs

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject

from galacteek import log

from galacteek.ipfs import ipfsOp

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.mimetype import MIMEType
from galacteek.ipfs.mimetype import detectMimeType

from galacteek.crypto.qrcode import IPFSQrDecoder


class ResourceAnalyzer(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = QApplication.instance()

    @ipfsOp
    async def __call__(self, ipfsop, pathRef):
        """
        :param IPFSPath ipfsPath
        """

        if isinstance(pathRef, IPFSPath):
            ipfsPath = pathRef
        elif isinstance(pathRef, str):
            ipfsPath = IPFSPath(pathRef, autoCidConv=True)
        else:
            raise ValueError('Invalid input value')

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

        if mimetype and mimetype.valid:
            return mimetype, statInfo

    @ipfsOp
    async def decodeQrCodes(self, ipfsop, path):
        try:
            data = await ipfsop.waitFor(
                ipfsop.client.cat(path), 12
            )

            if data is None:
                return

            # Decode the QR codes in the image if there's any
            qrDecoder = IPFSQrDecoder()
            if not qrDecoder:
                return

            return qrDecoder.decode(data)
        except aioipfs.APIError:
            pass
