import os.path
import weakref
from datetime import datetime
from datetime import timedelta

from PyQt5.QtWidgets import QApplication

from PyQt5.QtGui import QStandardItemModel

from PyQt5.QtCore import QUrl
from PyQt5.QtCore import Qt
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QMimeData
from PyQt5.QtCore import QDir
from PyQt5.QtCore import QFile
from PyQt5.QtCore import QModelIndex

from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.ipfsops import *
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.appsettings import *

from galacteek.core.modelhelpers import *
from galacteek.ui.i18n import *  # noqa
from galacteek.ui.helpers import *


def sampleQrCodes():
    dir = QDir(':/share/qr-codes')
    if dir.exists():
        for entry in dir.entryList():
            yield entry, QFile(':/share/qr-codes/{}'.format(entry))


class MFSItem(UneditableItem):
    def __init__(self, text, path=None, parenthash=None, icon=None,
                 parent=None):
        super(MFSItem, self).__init__(text, icon=icon)
        self._path = path
        self._parentHash = parenthash
        self._parentItem = weakref.ref(parent) if parent else None
        self._cidCache = []

    @property
    def parentItem(self):
        # Qt has .parent() but it will segfault your a** every time
        if self._parentItem:
            return self._parentItem()

    @property
    def cidCache(self):
        return self._cidCache

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, v):
        self._path = v

    @property
    def parentHash(self):
        return self._parentHash

    def hasCid(self, cid):
        return cid in self._cidCache

    def purgeCid(self, cid):
        try:
            self._cidCache.remove(cid)
        except Exception:
            pass

    def storeEntry(self, nameItem, sizeItem):
        if nameItem.cidString:
            self._cidCache.append(nameItem.cidString)

        self.appendRow([nameItem, sizeItem])

    def setParentHash(self, pHash):
        self._parentHash = pHash

    def childrenItems(self, type=None):
        for row in range(0, self.rowCount()):
            child = self.child(row, 0)

            if child:
                if type:
                    if isinstance(child, type):
                        yield child
                else:
                    yield child

    def findChildByCid(self, cid):
        for item in self.childrenItems():
            if not isinstance(item, MFSNameItem):
                continue
            if item.entry['Hash'] == cid:
                return item

    def findChildByName(self, name):
        for item in self.childrenItems():
            if isinstance(item, MFSNameItem):
                if item.entry['Name'] == name:
                    return item
            elif isinstance(item, MFSTimeFrameItem):
                if item.text() == name:
                    return item


class MFSRootItem(MFSItem):
    """
    Root item (top-level items in the MFS model)
    """

    expandedItemsCount = 0

    def __init__(self, text, path=None, parenthash=None, icon=None,
                 offline=False, alwaysOffline=False):
        super(MFSRootItem, self).__init__(text, path=path,
                                          parenthash=parenthash,
                                          icon=icon)

        # alwaysOffline won't be used by the filemanager for now
        self.offline = True if alwaysOffline else offline
        self.alwaysOffline = alwaysOffline

        # Root items have no CIDs
        self.cidString = None


class MFSTimeFrameItem(MFSItem):
    """
    Model item that holds MFS files which were written
    at a date corresponding to this item's time frame
    (right now it's a 1-day time frame but we can extend
    to 3-days or 1 week if it proves to be cumbersome in
    the UI)
    """

    def __init__(self, date, text, icon=None):
        super(MFSTimeFrameItem, self).__init__(text, icon=icon)

        self.date = date
        self.cidString = None

    def inRange(self, dateFrom, dateTo):
        return (self.date >= dateFrom and self.date <= dateTo)

    def isToday(self):
        return self.isDay(datetime.today())

    def isPast3Days(self):
        return any(
            self.isPastDay(d) is True for d in range(1, 4)
        )

    def isPastDay(self, bdays):
        return self.isDay(datetime.today() - timedelta(days=bdays))

    def isDay(self, day):
        return (day.year == self.date.year and
                day.month == self.date.month and
                day.day == self.date.day)


class MFSNameItem(MFSItem):
    def __init__(self, entry, text, icon, cidString, parent=None):
        super().__init__(text, icon=icon, parent=parent)

        self._entry = entry
        self._mimeType = None
        self._cidString = cidString

    @property
    def entry(self):
        return self._entry

    @property
    def cidString(self):
        return self._cidString

    @property
    def ipfsPath(self):
        return IPFSPath(self.fullPath)

    @property
    def qIpfsUrl(self):
        return QUrl(self.ipfsPath.ipfsUrl)

    @property
    def mimeType(self):
        return self._mimeType

    def mimeFromDb(self, db):
        self._mimeType = db.mimeTypeForFile(self.entry['Name'])

    def mimeDirectory(self, db):
        self._mimeType = db.mimeTypeForName('inode/directory')

    @property
    def mimeCategory(self):
        if self.mimeType:
            return self.mimeTypeName.split('/')[0]

    @property
    def mimeTypeName(self):
        if self.mimeType:
            return self.mimeType.name()

    @property
    def fullPath(self):
        parentHash = self.parentHash
        if parentHash:
            fp = joinIpfs(os.path.join(parentHash, self.entry['Name']))
        else:
            fp = joinIpfs(self.entry['Hash'])

        return fp + '/' if self.isDir() else fp

    def isFile(self):
        # XXX: MFS ls calls return type 0 for files, while
        # regular unixfs ls will return type 2
        # Since we use a mixed approach now (getting the
        # CID with files stat and then do a unixfs ls)
        # entry type for files is 2
        #
        # return self.entry['Type'] == 0

        return self.entry['Type'] == 2

    def isDir(self):
        return self.entry['Type'] == 1


class MFSItemModel(QStandardItemModel):
    # Drag and drop events
    fileDropEvent = pyqtSignal(str)
    directoryDropEvent = pyqtSignal(str)

    # An item's view was refreshed
    refreshed = pyqtSignal(MFSNameItem)

    needExpand = pyqtSignal(QModelIndex)

    # Specific roles
    CidRole = 0x0108
    TimeFrameRole = 0x0109
    FileNameRole = 0x010a

    def __init__(self):
        QStandardItemModel.__init__(self)
        self.app = QApplication.instance()

        self.itemRoot = self.invisibleRootItem()
        self.itemRootIdx = self.indexFromItem(self.itemRoot)
        self.initialized = False
        self.qrInitialized = False

    def setupItemsFromProfile(self, profile):
        self.itemHome = MFSRootItem(iHome(),
                                    path=profile.pathHome,
                                    icon=getIcon('go-home.png'))
        self.itemImages = MFSRootItem(iImages(),
                                      path=profile.pathImages,
                                      icon=getMimeIcon('image/x-generic'))
        self.itemPictures = MFSRootItem(iPictures(),
                                        path=profile.pathPictures,
                                        icon=getIcon('folder-pictures.png'))
        self.itemVideos = MFSRootItem(iVideos(),
                                      path=profile.pathVideos,
                                      icon=getIcon('folder-videos.png'))
        self.itemMusic = MFSRootItem(iMusic(),
                                     path=profile.pathMusic,
                                     icon=getIcon('folder-music.png'))
        self.itemCode = MFSRootItem(iCode(),
                                    path=profile.pathCode,
                                    icon=getIcon('code-fork.png'))
        self.itemDocuments = MFSRootItem(iDocuments(),
                                         path=profile.pathDocuments,
                                         icon=getIcon('folder-documents.png'))
        self.itemWebPages = MFSRootItem(iWebPages(),
                                        path=profile.pathWebPages,
                                        icon=getMimeIcon('text/html'))
        self.itemDWebApps = MFSRootItem(iDWebApps(),
                                        path=profile.pathDWebApps,
                                        icon=getIcon('distributed.png'))
        self.itemQrCodes = MFSRootItem(iQrCodes(),
                                       path=profile.pathQrCodes,
                                       icon=getIcon('ipfs-qrcode.png'))
        self.itemTemporary = MFSRootItem(iTemporaryFiles(),
                                         path=profile.pathTmp,
                                         icon=getIcon('folder-temp.png'))
        self.itemEncrypted = MFSRootItem(iEncryptedFiles(),
                                         path=profile.pathEncryptedFiles,
                                         icon=getIcon('key-diago.png'))

        # Core MFS folders (visible in the "Link to MFS" folders)
        self.fsCore = [
            self.itemHome,
            self.itemTemporary,
            self.itemPictures,
            self.itemImages,
            self.itemVideos,
            self.itemCode,
            self.itemMusic,
            self.itemDocuments,
            self.itemWebPages,
            self.itemDWebApps
        ]

        # Extra folders
        self.fsExtra = [
            self.itemQrCodes,
            self.itemEncrypted
        ]

        self.filesystem = self.fsCore + self.fsExtra
        self.itemRoot.appendRows(self.filesystem)
        self.initialized = True

    @ipfsOp
    async def setupQrCodesFolder(self, ipfsop, profile, model, files):
        """
        Import the sample QR codes to the corresponding folder
        Needs rewrite ..
        """
        for name, qrFile in sampleQrCodes():
            await ipfsop.sleep()

            if qrFile.exists():
                path = self.app.tempDir.filePath(name)
                if qrFile.copy(path):
                    tmpFile = QFile(path)
                    entry = await ipfsop.addPath(path)
                    await ipfsop.sleep()

                    if not entry:
                        tmpFile.remove()
                        continue

                    exists = await ipfsop.filesLookupHash(
                        model.itemQrCodes.path, entry['Hash'])

                    await ipfsop.sleep()

                    if not exists:
                        await files.linkEntryNoMetadata(
                            entry,
                            model.itemQrCodes.path,
                            entry['Name'])

                    tmpFile.remove()

        self.qrInitialized = True

    def displayItem(self, arg):
        self.itemRoot.appendRow(arg)

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction | \
            Qt.TargetMoveAction | Qt.LinkAction

    def mimeData(self, indexes):
        mimedata = QMimeData()

        for idx in indexes:
            if not idx.isValid():
                continue

            nameItem = self.getNameItemFromIdx(idx)

            if nameItem:
                mimedata.setUrls([nameItem.qIpfsUrl])
                break

        return mimedata

    def canDropMimeData(self, data, action, row, column, parent):
        mimeText = data.text()

        if mimeText and mimeText.startswith('file://'):
            return True
        return False

    def dropMimeData(self, data, action, row, column, parent):
        if data.hasUrls():
            for url in data.urls():
                path = url.toLocalFile()
                if os.path.isfile(path):
                    self.fileDropEvent.emit(path)
                if os.path.isdir(path):
                    self.directoryDropEvent.emit(path)
            return True
        else:
            return False

    def getHashFromIdx(self, idx):
        item = self.getNameItemFromIdx(idx)
        if item and hasattr(item, 'cidString'):
            return item.cidString

    def getNameFromIdx(self, idx):
        idxName = self.index(idx.row(), 0, idx.parent())
        if idxName.isValid():
            return self.data(idxName)

    def getNameItemFromIdx(self, idx):
        idxName = self.index(idx.row(), 0, idx.parent())
        if idxName.isValid():
            item = self.itemFromIndex(idxName)
            if isinstance(item, MFSNameItem):
                return item

    def findCidInModel(self, cid, parentItem, recursive=False):
        flags = Qt.MatchFixedString | Qt.MatchWrap

        if recursive:
            flags |= Qt.MatchRecursive

        return self.model.match(
            parentItem.index(),
            self.model.CidRole,
            cid,
            -1,
            flags)

    def itemFromCid(self, cid, parent=None):
        idxList = self.findCidInModel(
            cid, parent=parent if parent else self.itemRoot
        )
        if len(idxList) > 0:
            return self.itemFromIndex(idxList.pop())

    def data(self, index, role):
        if not index.isValid():
            return None

        item = self.itemFromIndex(index)

        if role == self.CidRole and isinstance(item, MFSNameItem):
            # For the CidRole we return the CID associated with the item
            return item.cidString
        elif role == self.TimeFrameRole and isinstance(item, MFSTimeFrameItem):
            return item.text()
        elif role == self.FileNameRole and isinstance(item, MFSNameItem):
            return item.text()
        else:
            return super().data(index, role)


def createMFSModel():
    # Setup the model
    model = MFSItemModel()
    model.setHorizontalHeaderLabels(
        [iFileName(), iFileSize()])
    return model
