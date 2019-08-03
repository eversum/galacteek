import functools
import os.path
import os
import aioipfs

from PyQt5 import QtWebEngineWidgets
from PyQt5.QtWebEngineWidgets import QWebEngineDownloadItem
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import QObject

from galacteek import log
from galacteek import logUser
from galacteek import ensure
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.crawl import runTitleParser
from galacteek.core.asynclib import asyncReadFile
from galacteek.core.asynclib import asyncWriteFile

from .helpers import questionBox
from ..appsettings import *
from .i18n import iUnknown


def iFinishedDownload(filename):
    return QCoreApplication.translate(
        'Galacteek', 'Finished downloading file {0}').format(filename)


def iStartingDownload(filename):
    return QCoreApplication.translate(
        'Galacteek', 'Downloading file {0} ..').format(filename)


def iPageSaved(title):
    return QCoreApplication.translate(
        'Galacteek',
        'Web page {0} was saved').format(title)


class DownloadsManager(QObject):
    def __init__(self, app):
        super(DownloadsManager, self).__init__()

        self.app = app
        self.webProfile = QtWebEngineWidgets.QWebEngineProfile.defaultProfile()
        self.webProfile.downloadRequested.connect(self.onDownloadRequested)

    def onDownloadRequested(self, downItem):
        if not downItem:
            return

        downloadsLoc = self.app.settingsMgr.eGet(S_DOWNLOADS_PATH)

        def progress(received, total):
            pass

        def finished(item):
            filename = item.path() or iUnknown()
            self.app.systemTrayMessage(
                'Galacteek', iFinishedDownload(filename))

        downPath = downItem.path()
        name = os.path.basename(downPath)
        autoDownloadFor = ['qwe_download']

        if name in autoDownloadFor:
            downItem.accept()
            return

        if downPath.startswith(self.app.tempDirWeb):
            downItem.finished.connect(
                functools.partial(self.pageSaved, downItem))
            downItem.accept()
            return

        reply = questionBox('Download', 'Download {} ?'.format(name))
        if reply is not True:
            downItem.cancel()
            return

        self.app.systemTrayMessage('Galacteek', iStartingDownload(name))

        downItem.setPath(os.path.join(downloadsLoc, name))
        downItem.finished.connect(functools.partial(finished, downItem))
        downItem.downloadProgress.connect(progress)
        downItem.accept()

    def pageSaved(self, downItem):
        saveFormat = downItem.savePageFormat()

        if saveFormat == QWebEngineDownloadItem.CompleteHtmlSaveFormat:
            ensure(self.pageSavedComplete(downItem))

    @ipfsOp
    async def pageSavedComplete(self, ipfsop, downItem):
        curProfile = ipfsop.ctx.currentProfile

        path = downItem.path()
        basedir = os.path.dirname(path)

        data = await asyncReadFile(path)
        if data is None:
            return

        # Rewrite links that have the gateway origin
        try:
            decoded = data.decode()
            params = self.app.getIpfsConnectionParams()
            replaced = decoded.replace(str(params.gatewayUrl), 'dweb:')
        except:
            # No rewrite
            pass
        else:
            await asyncWriteFile(path, replaced.encode())

        title = runTitleParser(data)
        if title is None:
            title = iUnknown()

        try:
            entry = await ipfsop.addPath(basedir)
        except aioipfs.APIError as err:
            log.debug('Cannot import saved page: {}'.format(err.message))
            return
        else:
            if entry is None:
                return

            multihash = entry.get('Hash')
            logUser.debug('Saved webpage to {}'.format(multihash))

            if curProfile and multihash:
                curProfile.webPageSaved.emit(entry, title)

            self.app.systemTrayMessage('Downloads', iPageSaved(title))
