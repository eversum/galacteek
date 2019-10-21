import os
import functools
import binascii
import multihash
import multibase

from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QIcon

from PyQt5.QtCore import QStandardPaths
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QSize
from PyQt5.QtCore import QEvent
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QDir
from PyQt5.QtCore import pyqtSignal

from PyQt5.QtWidgets import QStyle
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QVBoxLayout

from galacteek import ensure
from galacteek.ipfs.mimetype import mimeTypeDagUnknown
from galacteek.ipfs.mimetype import mimeTypeDagPb
from galacteek.ipfs.cidhelpers import getCID
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs import ipfsOpFn
from galacteek.ipfs import kilobytes


from .i18n import iIpfsQrCodes
from .i18n import iUnknown


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


async def getIconFromIpfs(ipfsop, ipfsPath, scaleWidth=None,
                          sizeMax=kilobytes(256), timeout=10):
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
        mimeType, stat = await app.rscAnalyzer(ipfsPath)
        if not mimeType or not stat:
            return None

        statInfo = StatInfo(stat)

        if not statInfo.valid or statInfo.dataLargerThan(sizeMax):
            return None
        elif not mimeType.isImage:
            return None

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


@ipfsOpFn
async def getImageFromIpfs(ipfsop, ipfsPath, timeout=10):
    try:
        imgData = await ipfsop.waitFor(
            ipfsop.client.cat(str(ipfsPath)), timeout
        )

        if not imgData:
            return None

        image = QImage()
        image.loadFromData(imgData)
        return image
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
    elif mimeType in [mimeTypeDagUnknown, mimeTypeDagPb]:
        mIcon = mimeType.type

    icon = getMimeIcon(mIcon)
    return icon if icon else getMimeIcon(
        defaultIcon if defaultIcon else 'unknown')


def getHomePath():
    pList = QStandardPaths.standardLocations(QStandardPaths.HomeLocation)
    return pList[0] if len(pList) > 0 else os.getenv('HOME')


def messageBox(message, title=None):
    from .clips import RotatingCubeClipSimple
    from .widgets import AnimatedButton

    app = QApplication.instance()
    msgBox = QDialog()

    largeSize = app.style().pixelMetric(QStyle.PM_LargeIconSize)

    button = AnimatedButton(
        RotatingCubeClipSimple(), ignoreFrameEvery=2, parent=msgBox)
    button.clicked.connect(functools.partial(msgBox.done, 1))
    button.setIconSize(QSize(largeSize, largeSize))
    button.clip.setSpeed(100)
    button.setText('OK')
    button.startClip()

    label = QLabel(message)
    label.setAlignment(Qt.AlignCenter)
    layout = QVBoxLayout()
    layout.addWidget(label)
    layout.addWidget(button)
    msgBox.setLayout(layout)
    msgBox.setMinimumSize(
        app.desktopGeometry.width() / 3,
        128
    )

    msgBox.setWindowTitle(title if title else 'galacteek: Message')
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


def inputTextLong(title='', label='', text='', parent=None):
    text, ok = QInputDialog.getText(
        parent, title, label, QLineEdit.Normal,
        text, Qt.Dialog, Qt.ImhNone)
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


def cidInfosMarkup(cidString):
    try:
        cid = getCID(cidString)
        mhash = multihash.decode(cid.multihash)
        baseEncoding = multibase.multibase.get_codec(cidString)
    except:
        return '<p>Invalid CID</p>'

    return '''
    <p>CID: <b>{cids}</b></p>
    <p>CID version {cidv}</p>
    <p>Multibase encoding: <b>{mbase}</b></p>

    <p>Codec: <b>{codec}</b></p>
    <p>Multihash function: <b>{mhashfunc}</b></p>
    <p>Multihash function code: {mhashfuncvalue}
        (<b>{mhashfuncvaluehex}</b>)</p>
    <p>Multihash digest: <b>{mhashdigest}</b></p>
    <p>Multihash: <b>{mhashascii}</b></p>
    '''.format(cids=cidString,
               cidv=cid.version,
               mbase=baseEncoding.encoding if baseEncoding else iUnknown(),
               codec=cid.codec,
               mhashfunc=mhash.func.name,
               mhashfuncvalue=mhash.func.value,
               mhashfuncvaluehex=hex(mhash.func.value),
               mhashdigest=binascii.b2a_hex(mhash.digest).decode('ascii'),
               mhashascii=binascii.b2a_hex(cid.multihash).decode('ascii'))
