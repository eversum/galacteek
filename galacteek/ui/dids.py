import functools

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QMenu

from galacteek import ensure
from galacteek import log
from galacteek.did.ipid import IPIdentifier
from galacteek.did.ipid import IPService

from .dialogs import GenericTextInputDialog
from .helpers import getIcon
from .helpers import runDialog


class DIDExplorer:
    def __init__(self):
        self.app = QApplication.instance()
        self.app.towers['did'].didServiceOpenRequest.connectTo(
            self.onDidServiceOpen)
        self.app.towers['did'].didServiceObjectOpenRequest.connectTo(
            self.onDidSrvObjectOpen)

    async def onDidSrvObjectOpen(self, did, serviceId, objectId):
        await self.app.resourceOpener.openIpServiceObject(
            serviceId, objectId
        )

    async def onDidServiceOpen(self, did, serviceId, ctx):
        log.debug('Accessing IP Service: {0} (DID: {1})'.format(
            did, serviceId))
        await self.app.resourceOpener.browseIpService(
            serviceId, ctx
        )


def addIpServiceCollection(ipid: IPIdentifier):
    def addService(dlg):
        name = dlg.enteredText()
        if name:
            ensure(ipid.addServiceCollection(name))

    runDialog(
        GenericTextInputDialog, 'Collection name',
        inputRegExp=r'[A-Za-z0-9\-_]+',
        maxLength=24, title='IP collection service',
        accepted=addService
    )


async def buildIpServicesMenu(ipid: IPIdentifier,
                              sMenu,
                              parent=None):
    app = QApplication.instance()
    didTower = app.towers['did']

    if ipid.local:
        action = QAction(
            getIcon('blocks-cluster.png'),
            'Add collection service',
            sMenu)

        action.triggered.connect(functools.partial(
            addIpServiceCollection, ipid
        ))

        sMenu.addAction(action)
        sMenu.addSeparator()

    async for service in ipid.discoverServices():
        if service.type == IPService.SRV_TYPE_COLLECTION:
            menu = QMenu(str(service), sMenu)
            menu.setIcon(getIcon('ipservice.png'))

            async for obj in service.contained():
                action = QAction(
                    getIcon('ipfs-cube-64.png'),
                    obj['name'],
                    menu)
                action.setData({
                    'service': service,
                    'ctx': {
                        'path': obj['path']
                    }
                })

                def emitObjectOpen(tower, did, serviceId, objectId):
                    ensure(tower.didServiceObjectOpenRequest.emit(
                        did, serviceId, objectId
                    ))

                action.triggered.connect(
                    functools.partial(
                        emitObjectOpen, didTower,
                        ipid.did, service.id, obj['id']
                    )
                )

                menu.addAction(action)

            sMenu.addMenu(menu)
        else:
            action = QAction(
                getIcon('ipservice.png'),
                str(service),
                sMenu)
            action.setData({
                'service': service,
                'ctx': {}
            })

            def emitOpen(tower, did, serviceId):
                ensure(tower.didServiceOpenRequest.emit(
                    did, serviceId, {})
                )

            action.triggered.connect(
                functools.partial(emitOpen, didTower, ipid.did, service.id)
            )

            action.setToolTip(service.id)
            sMenu.addAction(action)
            sMenu.addSeparator()

    return sMenu


async def buildPublishingMenu(ipid: IPIdentifier, parent=None):
    didPublishMenu = QMenu('DID publish', parent)
    didPublishMenu.setToolTipsVisible(True)
    didPublishMenu.setIcon(getIcon('ipservice.png'))

    async for service in ipid.discoverServices():
        if service.type == IPService.SRV_TYPE_COLLECTION:
            action = QAction(
                getIcon('ipservice.png'),
                str(service),
                didPublishMenu)
            action.setData({
                'service': service,
                'ctx': {}
            })
            didPublishMenu.addAction(action)

    return didPublishMenu
