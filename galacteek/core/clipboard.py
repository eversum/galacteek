import os.path
import time
import collections

from PyQt5.QtGui import QClipboard
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QDateTime

from galacteek import ensure
from galacteek import log
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.mimetype import detectMimeType
from galacteek.ipfs.mimetype import MIMEType


class ClipboardItem(QObject):
    mimeTypeDetected = pyqtSignal(MIMEType)
    mimeTypeAvailable = pyqtSignal(MIMEType)
    mimeIconAvailable = pyqtSignal()
    statRetrieved = pyqtSignal(dict)
    ipnsNameResolved = pyqtSignal(IPFSPath)

    def __init__(self, ipfsPath, mimeType=None, parent=None):
        super(ClipboardItem, self).__init__(parent)

        self._ipfsPath = ipfsPath
        self._resolvedPath = None
        self._mimeType = mimeType
        self._statInfo = None
        self._cid = None
        self._ts = time.time()
        self._date = QDateTime.currentDateTime()
        self._mimeIcon = None

        self.mimeTypeDetected.connect(self.setMimeType)
        self.statRetrieved.connect(self.statInfo)

    @property
    def ts(self):
        return self._ts

    @property
    def date(self):
        return self._date

    @property
    def path(self):
        # Object path (without fragment)
        return self._ipfsPath.objPath

    @property
    def fullPath(self):
        # Full path (with fragment)
        return self._ipfsPath.fullPath

    @property
    def ipfsPath(self):
        return self._ipfsPath

    @property
    def resolvedPath(self):
        return self._resolvedPath

    @property
    def fragment(self):
        return self._ipfsPath.fragment

    @property
    def basename(self):
        return os.path.basename(self.path)

    @property
    def cid(self):
        return self._cid

    @property
    def mimeType(self):
        return self._mimeType

    @property
    def mimeCategory(self):
        if isinstance(self.mimeType, MIMEType):
            return self.mimeType.category

    @property
    def mimeIcon(self):
        return self._mimeIcon

    @mimeIcon.setter
    def mimeIcon(self, icon):
        self._mimeIcon = icon
        self.mimeIconAvailable.emit()

    @property
    def stat(self):
        return self._statInfo

    @property
    def clipInput(self):
        return self._ipfsPath.input

    @property
    def valid(self):
        return isinstance(self.mimeType, MIMEType) and self.stat is not None

    def setMimeType(self, mimeType):
        log.debug('Detected mime-type {type} for {path}'.format(
            path=self.path, type=str(mimeType)))
        self._mimeType = mimeType
        self.mimeTypeAvailable.emit(mimeType)

    def statInfo(self, stat):
        self._statInfo = stat
        self._cid = stat.get('Hash', None)

    def __str__(self):
        return self.path

    def __repr__(self):
        return '{ts} {path}: mime {mimetype}, stat {stat}'.format(
            ts=self.ts,
            path=self.path,
            mimetype=self.mimeType,
            stat=self.stat
        )


class ClipboardTracker(QObject):
    """
    Tracks the system's clipboard activity and emits signals
    depending on whether or not the clipboard contains an IPFS CID or path
    """

    clipboardPathProcessed = pyqtSignal(IPFSPath)
    clipboardHistoryChanged = pyqtSignal()  # not used anymore
    clipboardPathInvalid = pyqtSignal(IPFSPath)

    itemRegister = pyqtSignal(ClipboardItem, bool)
    itemAdded = pyqtSignal(ClipboardItem)
    itemRemoved = pyqtSignal(ClipboardItem)
    currentItemChanged = pyqtSignal(ClipboardItem)

    def __init__(self, app, clipboard, maxItems=256):
        super(ClipboardTracker, self).__init__()

        self.app = app
        self.clipboard = clipboard

        self._current = None
        self._items = collections.deque(maxlen=maxItems)
        self.itemRegister.connect(self.addItem)

        self.clipboard.changed.connect(self.onClipboardChanged)
        self.clipboardPathProcessed.connect(self.onValidPath)

    @property
    def items(self):
        return self._items

    @property
    def current(self):
        return self._current

    @current.setter
    def current(self, item):
        self._current = item
        self.currentItemChanged.emit(item)

        if item.mimeType:
            item.mimeTypeAvailable.emit(item.mimeType)

    def __len__(self):
        return len(self.items)

    def addItem(self, obj, setToCurrent):
        self._items.append(obj)

        if setToCurrent:
            self.current = obj

        self.itemAdded.emit(obj)

    def exists(self, ipfsPath):
        """
        :param IPFSPath ipfsPath: path object
        :rtype: bool
        """

        return self.getByPath(ipfsPath) is not None

    def getByPath(self, ipfsPath):
        for obj in self.items:
            if obj.ipfsPath == ipfsPath:
                return obj

    def removeItem(self, item):
        if self.exists(item.path):
            try:
                self.items.remove(item)
                self.itemRemoved.emit(item)
            except BaseException:
                return

    def onClipboardChanged(self, mode):
        text = self.clipboard.text(mode)
        self.clipboardProcess(text, clipboardMode=mode)

    def clipboardProcess(self, text, clipboardMode=None):
        """
        Process the contents of the clipboard. If it is a valid CID/path,
        emit a signal, processed by the main window for the clipboard
        manager
        """

        if not isinstance(text, str) or len(text) > 1024:
            return

        text = text.strip()

        path = IPFSPath(text, autoCidConv=True)
        if path.valid:
            self.clipboardPathProcessed.emit(path)
        else:
            self.clipboardPathInvalid.emit(path)

    def getHistory(self):
        return list(self.items)

    def clearHistory(self):
        for item in self._items:
            self.itemRemoved.emit(item)
        self._items.clear()
        self._current = None

    def getCurrent(self):
        """ Returns current clipboard item """
        return self.current

    def clipboardInit(self):
        pass

    def clipboardPreferredMode(self):
        return QClipboard.Selection if self.clipboard.supportsSelection() \
            else QClipboard.Clipboard

    def setText(self, text):
        """ Sets the clipboard's text content """
        self.clipboard.setText(text, self.clipboardPreferredMode())

    def getText(self):
        """ Returns clipboard's text content from the preferred source """
        return self.clipboard.text(self.clipboardPreferredMode())

    def onValidPath(self, ipfsPath):
        existing = self.getByPath(ipfsPath)

        if not existing:
            item = ClipboardItem(ipfsPath, parent=self)
            self.itemRegister.emit(item, True)
            ensure(self.scanItem(item))
        else:
            # Set existing item as current item
            self.current = existing

    @ipfsOp
    async def streamResolve(self, ipfsop, item, count=2):
        matches = []
        async for entry in ipfsop.nameResolveStream(
                item.ipfsPath.objPath, timeout='10s'):
            matches.append(entry.get('Path'))
            if len(matches) > count:
                break

        if len(matches) > 0:
            latest = matches[-1]
            if isinstance(latest, str):
                item._resolvedPath = IPFSPath(latest, autoCidConv=True)
                item.ipnsNameResolved.emit(item.resolvedPath)
                return item.resolvedPath

    @ipfsOp
    async def scanItem(self, ipfsop, cItem):
        mimetype = None
        path = cItem.path
        mHashMeta = await self.app.multihashDb.get(path)

        if cItem.ipfsPath.isIpnsRoot:
            rPath = await self.streamResolve(cItem)
            if rPath:
                path = str(rPath)

        if mHashMeta:
            # Already have metadata for this object
            value = mHashMeta.get('mimetype')
            if value:
                mimetype = MIMEType(value)
            else:
                mimetype = await detectMimeType(path)

            statInfo = mHashMeta.get('stat')
            if statInfo:
                cItem.statRetrieved.emit(statInfo)
        else:
            mimetype = await detectMimeType(path)

            statInfo = await ipfsop.objStat(path)
            if not statInfo or not isinstance(statInfo, dict):
                log.debug('Stat failed for {path}'.format(
                    path=path))
                return
            else:
                cItem.statRetrieved.emit(statInfo)

            await ipfsop.sleep()

            # Store retrieved information in the metadata store
            metadata = {}

            if mimetype and mimetype.valid:
                metadata['mimetype'] = str(mimetype)
            if statInfo and isinstance(statInfo, dict):
                metadata['stat'] = statInfo

            if len(metadata) > 0:
                await self.app.multihashDb.store(
                    path,
                    **metadata
                )

        if mimetype and mimetype.valid:
            cItem.mimeTypeDetected.emit(mimetype)
