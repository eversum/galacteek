import os

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QAbstractListModel
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QMimeData
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QVariant

from galacteek.ipfs.cidhelpers import getCID
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import cidConvertBase32

from galacteek.ui.helpers import getIcon
from galacteek.ui.helpers import getMimeIcon
from galacteek.ui.helpers import sizeFormat

from galacteek.ui.i18n import iUnixFSFileToolTip


class UnixFSEntryInfo:
    def __init__(self, entry, parentCid):
        self._entry = entry
        self._parentCid = parentCid

    @property
    def entry(self):
        return self._entry

    @property
    def filename(self):
        return self.entry['Name']

    @property
    def sizeFormatted(self):
        return sizeFormat(self.entry['Size'])

    @property
    def ipfsPath(self):
        return IPFSPath(self.getFullPath(), autoCidConv=True)

    @property
    def mimeType(self):
        return self._mimeType

    def mimeFromDb(self, db):
        if self.isDir():
            self._mimeType = 'application/x-directory'
        elif self.isFile():
            mType = db.mimeTypeForFile(self.entry['Name'])
            if mType:
                self._mimeType = mType.name()
        elif self.isRaw():
            self._mimeType = 'application/octet-stream'
        else:
            # application/unknown ?
            self._mimeType = 'application/octet-stream'

    @property
    def mimeCategory(self):
        if self.mimeType:
            return self.mimeType.split('/')[0]

    @property
    def cid(self):
        return self.entry['Hash']

    @property
    def cidObject(self):
        return getCID(self.cid)

    def getFullPath(self):
        """
        Returns the full IPFS path of the entry associated with this item
        (preserving file names) if we have the parent's hash, or the IPFS path
        with the entry's hash otherwise
        """

        if self._parentCid:
            return joinIpfs(os.path.join(cidConvertBase32(self._parentCid),
                                         self.filename))
        else:
            return joinIpfs(cidConvertBase32(self.entry['Hash']))

    def isRaw(self):
        return self.entry['Type'] == 0

    def isDir(self):
        return self.entry['Type'] == 1

    def isFile(self):
        return self.entry['Type'] == 2

    def isMetadata(self):
        return self.entry['Type'] == 3

    def isSymlink(self):
        return self.entry['Type'] == 4

    def isUnknown(self):
        return self.entry['Type'] == -1


class UnixFSDirectoryModel(QAbstractListModel):
    COL_UNIXFS_NAME = 0
    COL_UNIXFS_SIZE = 1
    COL_UNIXFS_MIME = 2
    COL_UNIXFS_HASH = 3

    def __init__(self, parent=None):
        super(UnixFSDirectoryModel, self).__init__(parent)

        self.app = QApplication.instance()
        self.entries = []

        self.iconFolder = getIcon('folder-open.png')
        self.iconFile = getIcon('file.png')
        self.iconUnknown = getIcon('unknown-file.png')

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def mimeData(self, indexes):
        mimedata = QMimeData()

        urls = []
        for idx in indexes:
            if not idx.isValid():
                continue

            eInfo = self.getUnixFSEntryInfoFromIdx(idx)

            if eInfo:
                url = QUrl(eInfo.ipfsPath.ipfsUrl)
                urls.append(url)

        mimedata.setUrls(urls)
        return mimedata

    def canDropMimeData(self, data, action, row, column, parent):
        return True

    def clearModel(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.entries))
        self.entries.clear()
        self.endRemoveRows()

    def getHashFromIdx(self, idx):
        eInfo = self.getUnixFSEntryInfoFromIdx(idx)
        if eInfo:
            return eInfo.cid

    def rowCount(self, parent):
        return len(self.entries)

    def columnCount(self, parent):
        return 1

    def getUnixFSEntryInfoFromIdx(self, idx):
        try:
            return self.entries[idx.row()]
        except IndexError:
            return None

    def formatEntries(self):
        doc = []

        for eInfo in self.entries:
            doc.append(eInfo.entry)
        return doc

    def data(self, index, role):
        if not index.isValid():
            return QVariant(None)

        row = index.row()
        col = index.column()

        eInfo = self.getUnixFSEntryInfoFromIdx(index)

        if role == Qt.DisplayRole:
            if row > len(self.entries):
                return QVariant(None)

            if col == self.COL_UNIXFS_NAME:
                return QVariant(eInfo.filename)
            elif col == self.COL_UNIXFS_SIZE:
                return eInfo.entry['Size']
            elif col == self.COL_UNIXFS_MIME:
                return eInfo.mimeType
            elif col == self.COL_UNIXFS_HASH:
                return eInfo.cid
        elif role == Qt.DecorationRole:
            if eInfo.isDir():
                return self.iconFolder
            elif eInfo.isFile():
                if eInfo.mimeType:
                    mIcon = getMimeIcon(eInfo.mimeType)
                    if mIcon:
                        return mIcon
                    else:
                        return self.iconFile
                else:
                    return self.iconUnknown
        if role == Qt.ToolTipRole:
            return iUnixFSFileToolTip(eInfo)

    def searchByFilename(self, filename):
        return self.match(
            self.index(0, 0, QModelIndex()),
            Qt.DisplayRole,
            filename,
            -1,
            Qt.MatchContains | Qt.MatchWrap | Qt.MatchRecursive
        )
