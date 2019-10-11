import os.path
import aiofiles
import asyncio
import json
import functools

from PyQt5.QtWidgets import QToolBar
from PyQt5.QtCore import QCoreApplication
from PyQt5.Qt import QSizePolicy

from galacteek import ensure
from galacteek import log
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs import kilobytes
from galacteek.ipfs.cidhelpers import IPFSPath

from .helpers import getIcon
from .helpers import getMimeIcon
from .helpers import getIconFromIpfs
from .helpers import getIconFromImageData
from .helpers import getIconFromMimeType
from .helpers import getFavIconFromDir
from .widgets import HashmarkToolButton
from .widgets import IPFSObjectToolButton
from .widgets import URLDragAndDropProcessor

from .i18n import iUnknown


def iQuickAccess():
    return QCoreApplication.translate(
        'toolbarQa',
        '''<p><b>Quick Access</b> toolbar</p>
           <p>Drag and drop hashmarks and IPFS objects that
           you want to have easy access to</p>
        ''')


class QuickAccessToolBar(QToolBar, URLDragAndDropProcessor):
    """
    Quick Access toolbar, child of the main toolbar
    """

    def __init__(self, parent, configName='quickaccess1'):
        super(QuickAccessToolBar, self).__init__(parent=parent)

        self.app = QCoreApplication.instance()
        self.lock = asyncio.Lock(loop=self.app.loop)
        self.configFilePath = os.path.join(
            self.app.uiDataLocation, '{}.json'.format(configName))
        self.setObjectName('toolbarQa')
        self.setToolTip(iQuickAccess())
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumWidth(400)
        self.setAcceptDrops(True)
        self.analyzer = self.app.rscAnalyzer
        self._config = {
            'objects': []
        }

        self.ipfsObjectDropped.connect(self.onIpfsDrop)

    @property
    def config(self):
        return self._config

    async def save(self):
        try:
            async with aiofiles.open(self.configFilePath, 'w+t') as fd:
                await fd.write(json.dumps(self.config, indent=4))
        except Exception:
            log.debug('Could not save quickaccess config')

    async def load(self):
        try:
            async with aiofiles.open(self.configFilePath, 'rt') as fd:
                data = await fd.read()
                config = json.loads(data)

            if 'objects' not in config or not isinstance(
                    config['objects'], list):
                raise ValueError('Invalid config')

            self._config = config
        except:
            self._config = {
                'objects': []
            }
            self.registerDefaults()
            await self.save()

    def registerDefaults(self):
        self.registerFromMarkMeta({
            'title': 'Hardbin'})
        self.registerFromMarkMeta({
            'description': 'Distributed wikipedia.*english'})
        self.registerFromMarkMeta({
            'title': 'IPFessay'})
        self.registerFromMarkMeta({
            'title': 'IPLD explorer'})
        self.registerFromMarkMeta({
            'title': 'markup.rocks'})

    def onIpfsDrop(self, ipfsPath):
        if str(ipfsPath) not in self.config['objects']:
            ensure(self.processObject(ipfsPath))

    async def processObject(self, ipfsPath):
        path = str(ipfsPath)

        try:
            mark = self.app.marksLocal.find(path)
            if not mark:
                # Quick access without hashmark
                await self.registerSimple(ipfsPath)
            else:
                await self.registerHashmark(mark)
        except Exception as err:
            log.debug('Error while processing object: {0} {1}'.format(
                ipfsPath, str(err)))

    def registerFromMarkMeta(self, metadata):
        mark = self.app.marksLocal.searchByMetadata(metadata)
        if not mark:
            return

        if mark.path not in self.config['objects']:
            self.config['objects'].append(mark.path)

    async def findIcon(self, ipfsop, ipfsPath, rscStat, mimeType,
                       maxIconSize=kilobytes(512)):
        icon = None
        statInfo = StatInfo(rscStat)

        if statInfo.valid and mimeType.isImage:
            if statInfo.dataSmallerThan(maxIconSize):
                await ipfsop.sleep()

                data = await ipfsop.catObject(str(ipfsPath), timeout=5)
                if data:
                    icon = getIconFromImageData(data)
            else:
                icon = getMimeIcon('image/x-generic')
        elif mimeType.isDir:
            favIcon = await getFavIconFromDir(ipfsop, ipfsPath)
            if favIcon:
                icon = favIcon
            else:
                icon = getMimeIcon('inode/directory')
        else:
            await ipfsop.sleep()
            icon = getIconFromMimeType(mimeType)

        if icon is None:
            icon = getIcon('unknown-file.png')

        return icon

    @ipfsOp
    async def registerSimple(self, ipfsop, ipfsPath,
                             maxIconSize=kilobytes(512)):
        """
        Register an object in the toolbar without any hashmark associated
        """

        path = str(ipfsPath)
        result = await self.analyzer(ipfsPath)
        if result is None:
            return

        mimeType, rscStat = result

        if mimeType:
            icon = await self.findIcon(ipfsop, ipfsPath, rscStat, mimeType)
        else:
            icon = getIcon('unknown-file.png')

        button = IPFSObjectToolButton(ipfsPath, parent=self, icon=icon)
        action = self.addWidget(button)
        button.setToolTip('{0} ({1})'.format(
            str(ipfsPath), mimeType.type if mimeType else iUnknown()))
        button.clicked.connect(
            lambda: ensure(self.app.resourceOpener.open(
                str(ipfsPath), openingFrom='qa')))
        button.deleteRequest.connect(
            functools.partial(self.onDelete, button, action, str(ipfsPath)))

        if path not in self.config['objects']:
            self.config['objects'].append(path)
            await self.save()

    @ipfsOp
    async def registerHashmark(self, ipfsop, mark, maxIconSize=512 * 1024):
        """
        Register an object in the toolbar with an associated hashmark
        """

        ipfsPath = IPFSPath(mark.path)
        if not ipfsPath.valid:
            return

        mPath = str(ipfsPath)
        result = await self.analyzer(ipfsPath)
        if result is None:
            return

        mimeType, rscStat = result

        mIcon = mark.markData.get('icon', None)
        icon = None

        if mIcon and IPFSPath(mIcon).valid:
            stat = await ipfsop.objStat(mIcon)

            statInfo = StatInfo(stat)

            # Check filesize from the stat on the object
            if statInfo.valid and statInfo.dataSmallerThan(maxIconSize):
                icon = await getIconFromIpfs(ipfsop, mIcon)

                if icon is None:
                    icon = getIcon('unknown-file.png')
                else:
                    if not await ipfsop.isPinned(mIcon):
                        log.debug('Pinning icon {0}'.format(mIcon))
                        await ipfsop.ctx.pin(mIcon)
        elif mimeType:
            icon = await self.findIcon(ipfsop, ipfsPath, rscStat, mimeType)
        else:
            icon = getIcon('unknown-file.png')

        button = HashmarkToolButton(mark, parent=self, icon=icon)
        action = self.addWidget(button)
        button.setToolTip(mark.markData['metadata'].get('title', iUnknown()))
        button.clicked.connect(
            lambda: ensure(self.app.resourceOpener.open(
                str(ipfsPath), openingFrom='qa')))
        button.deleteRequest.connect(
            functools.partial(self.onDelete, button, action, mPath))

        if mPath not in self.config['objects']:
            self.config['objects'].append(mPath)
            await self.save()

    def onDelete(self, button, action, mPath):
        try:
            self._config['objects'].remove(mPath)
            self.removeAction(action)
            del button
        except:
            pass
        else:
            ensure(self.save())

    async def init(self):
        """
        Add some apps and links to the quickaccess bar
        """

        await self.load()

        for path in self.config['objects']:
            await asyncio.sleep(0.05)

            ipfsPath = IPFSPath(path)
            if not ipfsPath.valid:
                continue

            mark = self.app.marksLocal.find(str(ipfsPath))
            if mark:
                await self.registerHashmark(mark)
            else:
                await self.registerSimple(ipfsPath)

        await self.save()
