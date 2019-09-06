import os
import functools

from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QIcon

from PyQt5.QtCore import QStandardPaths
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QEvent
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QDir
from PyQt5.QtCore import pyqtSignal

from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QMenu

from galacteek import ensure
from galacteek.ipfs.mimetype import mimeTypeDag

from .i18n import iIpfsQrCodes


def getIcon(iconName):
    app = QApplication.instance()
    if iconName in app._icons:
        return app._icons[iconName]

    if iconName.startswith(':/'):
        iconPath = iconName
    else:
        iconPath = ':/share/icons/{}'.format(iconName)

    icon = app._icons[iconName] = QIcon(QPixmap(iconPath))
    return icon


def getMimeIcon(mType):
    app = QApplication.instance()
    return app.mimeTypeIcons.get(mType)


def preloadMimeIcons():
    icons = {}
    mIconsDir = QDir(':/share/icons/mimetypes')

    if not mIconsDir.exists():
        return icons

    entries = mIconsDir.entryList()

    for entry in entries:
        mType = entry.replace('.png', '').replace('-', '/', 1)
        icons[mType] = getIcon('mimetypes/{}'.format(entry))

    return icons


async def getIconFromIpfs(ipfsop, ipfsPath, scaleWidth=None, timeout=10):
    """
    We cache the icons that we got out of the IPFS repo by their path
    Max icons cached is set by 'ipfsIconsCacheMax' in the app object
    """
    app = QApplication.instance()
    iconsCache = app.ipfsIconsCache

    if ipfsPath in iconsCache:
        # Already cached
        return iconsCache[ipfsPath]

    if len(iconsCache) >= app.ipfsIconsCacheMax:
        # FIFO 1/8
        for icount in range(0, int(app.ipfsIconsCacheMax / 8)):
            out = list(iconsCache.keys())[0]
            del iconsCache[out]

    try:
        imgData = await ipfsop.waitFor(
            ipfsop.client.cat(ipfsPath), timeout
        )

        if not imgData:
            return None

        icon = getIconFromImageData(imgData, scaleWidth=scaleWidth)
        if icon:
            iconsCache[ipfsPath] = icon
            return icon
    except BaseException:
        return None


async def getFavIconFromDir(ipfsop, ipfsPath, timeout=10):
    """
    If a favicon.ico file exists inside the given directory,
    return it in the form of a QIcon
    """

    faviconPath = ipfsPath.child('favicon.ico')
    try:
        stat = await ipfsop.objStat(str(faviconPath))

        if stat:
            # favicon exists
            return await getIconFromIpfs(ipfsop, str(faviconPath))
    except BaseException:
        return None


def getIconFromImageData(imgData, scaleWidth=None):
    try:
        img = QImage()
        img.loadFromData(imgData)

        if isinstance(scaleWidth, int):
            img = img.scaledToWidth(scaleWidth)

        return QIcon(QPixmap.fromImage(img))
    except BaseException:
        return None


def getIconIpfsIce():
    return getIcon('ipfs-logo-128-ice.png')


def getIconIpfsWhite():
    return getIcon('ipfs-logo-128-white.png')


def getIconIpfs64():
    return getIcon('ipfs-cube-64.png')


def getIconClipboard():
    return getIcon('clipboard.png')


def getIconFromMimeType(mimeType, defaultIcon=None):
    if not mimeType.valid:
        return getMimeIcon('unknown')

    fIcon = getMimeIcon(mimeType.type)
    if fIcon:
        return fIcon

    mIcon = None
    if mimeType.isDir:
        mIcon = 'inode/directory'
    elif mimeType.isHtml:
        mIcon = 'text/html'
    elif mimeType.isText:
        mIcon = 'text/plain'
    elif mimeType.isImage:
        mIcon = 'image/x-generic'
    elif mimeType.isVideo:
        mIcon = 'video/x-generic'
    elif mimeType.isAudio:
        mIcon = 'audio/x-generic'
    elif mimeType == mimeTypeDag:
        mIcon = mimeTypeDag.type

    icon = getMimeIcon(mIcon)
    return icon if icon else getMimeIcon(
        defaultIcon if defaultIcon else 'unknown')


def getHomePath():
    pList = QStandardPaths.standardLocations(QStandardPaths.HomeLocation)
    return pList[0] if len(pList) > 0 else os.getenv('HOME')


def messageBox(message, richText=False, title=None):
    msgBox = QMessageBox()
    msgBox.setText(message)

    if richText:
        msgBox.setTextFormat(Qt.RichText)

    if title:
        msgBox.setWindowTitle(title)

    msgBox.show()
    return msgBox.exec_()


def questionBox(title, text, parent=None):
    box = QMessageBox.question(parent, title, text)
    return box == QMessageBox.Yes


def directorySelect(caption=''):
    return QFileDialog.getExistingDirectory(
        None, caption, getHomePath(), QFileDialog.ShowDirsOnly)


def filesSelect(filter='(*.*)'):
    result = QFileDialog.getOpenFileNames(None,
                                          '', getHomePath(), filter)
    if result:
        return result[0]


def filesSelectImages():
    return filesSelect(
        filter='Images (*.xpm *.jpg *.jpeg *.png *.svg)')


def saveFileSelect(filter='(*.*)'):
    result = QFileDialog.getSaveFileName(None,
                                         '', getHomePath(), filter)
    if result:
        return result[0]


def disconnectSig(sig, target):
    try:
        sig.disconnect(target)
    except Exception:
        pass


def runDialog(cls, *args, **kw):
    title = kw.pop('title', None)
    accepted = kw.pop('accepted', None)
    dlgW = cls(*args, **kw)

    def onAccept():
        if accepted:
            accepted(dlgW)
    if title:
        dlgW.setWindowTitle(title)
    if accepted:
        dlgW.accepted.connect(functools.partial(accepted, dlgW))

    dlgW.show()
    dlgW.exec_()
    return dlgW


def inputText(title='', label='', parent=None):
    text, ok = QInputDialog.getText(parent, title, label)
    if ok:
        return text


class IPFSTreeKeyFilter(QObject):
    deletePressed = pyqtSignal()
    copyHashPressed = pyqtSignal()
    copyPathPressed = pyqtSignal()
    explorePressed = pyqtSignal()
    returnPressed = pyqtSignal()
    backspacePressed = pyqtSignal()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            modifiers = event.modifiers()

            key = event.key()
            if key == Qt.Key_Return:
                self.returnPressed.emit()
                return True
            if key == Qt.Key_Backspace:
                self.backspacePressed.emit()
                return True
            if modifiers & Qt.ControlModifier:
                if key == Qt.Key_C or key == Qt.Key_Y:
                    self.copyPathPressed.emit()
                    return True
                if key == Qt.Key_A:
                    self.copyHashPressed.emit()
                    return True
                if key == Qt.Key_X:
                    self.explorePressed.emit()
                    return True
            if event.key() == Qt.Key_Delete:
                self.deletePressed.emit()
                return True
        return False


class BasicKeyFilter(QObject):
    deletePressed = pyqtSignal()
    copyPressed = pyqtSignal()
    returnPressed = pyqtSignal()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            modifiers = event.modifiers()

            key = event.key()
            if key == Qt.Key_Return:
                self.returnPressed.emit()
            if modifiers & Qt.ControlModifier:
                if key == Qt.Key_C:
                    self.copyPressed.emit()

            if event.key() == Qt.Key_Delete:
                self.deletePressed.emit()
            return True
        return False


def clipboardSupportsSelection():
    return QApplication.clipboard().supportsSelection()


def sizeFormat(size):
    if size > (1024 * 1024 * 1024):
        return '{0:.2f} Gb'.format(size / (1024 * 1024 * 1024))
    if size > (1024 * 1024):
        return '{0:.2f} Mb'.format(size / (1024 * 1024))
    if size > 1024:
        return '{0:.2f} kb'.format(size / 1024)
    if size == 0:
        return '0'
    return '{0} bytes'.format(size)


def qrCodesMenuBuilder(urls, resourceOpener, parent=None):
    if isinstance(urls, list):
        icon = getIcon('ipfs-qrcode.png')
        menu = QMenu(iIpfsQrCodes(), parent)
        menu.setIcon(icon)

        for url in urls:
            menu.addAction(
                icon, str(url), functools.partial(
                    ensure, resourceOpener.open(url)))
        return menu
