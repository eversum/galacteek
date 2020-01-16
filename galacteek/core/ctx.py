import asyncio
import re
import collections
import time
import os.path

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QObject

from galacteek import log
from galacteek import logUser
from galacteek import GALACTEEK_NAME
from galacteek import ensure
from galacteek import ensureLater
from galacteek import partialEnsure
from galacteek import AsyncSignal

from galacteek.ipfs import pinning
from galacteek.ipfs import kilobytes
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs.cidhelpers import stripIpfs
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.pubsub.messages import ChatRoomMessage
from galacteek.ipfs.pubsub.service import PSMainService
from galacteek.ipfs.pubsub.service import PSChatService
from galacteek.ipfs.pubsub.service import PSHashmarksExchanger
from galacteek.ipfs.pubsub.service import PSPeersService

from galacteek.ipfs.ipfsops import *
from galacteek.ipfs import tunnel

from galacteek.did.ipid import ipidFormatValid
from galacteek.did.ipid import IPIdentifier

from galacteek.core.profile import UserProfile
from galacteek.core.softident import gSoftIdent
from galacteek.core.iphandle import SpaceHandle

from galacteek.crypto.rsa import RSAExecutor


class PeerCtx:
    def __init__(self, ipfsCtx, peerId, identMsg,
                 ipIdentifier: IPIdentifier,
                 pinglast=0, pingavg=0,
                 validated=False,
                 authenticated=False):
        self._ipfsCtx = ipfsCtx
        self._ipid = ipIdentifier
        self.peerId = peerId
        self.ident = identMsg
        self.pinglast = pinglast
        self.pingavg = pingavg
        self._identLast = int(time.time())
        self._validated = validated
        self._authenticated = authenticated

        self.sInactive = AsyncSignal(str)

    @property
    def ipfsCtx(self):
        return self._ipfsCtx

    @property
    def ident(self):
        return self._ident

    @property
    def ipid(self):
        return self._ipid

    @property
    def spaceHandle(self):
        return SpaceHandle(self.ident.iphandle)

    @property
    def identLast(self):
        return self._identLast

    @property
    def validated(self):
        return self._validated

    @property
    def authenticated(self):
        return self._authenticated

    @property
    def peerUnresponsive(self):
        return (int(time.time()) - self.identLast) > (60 * 5)

    @ident.setter
    def ident(self, v):
        self._ident = v
        self._identLast = int(time.time())

    def debug(self, msg):
        log.debug('Peer {p}@{ipid}: {msg}'.format(
            p=self.peerId, ipid=self.ipid.did, msg=msg))

    @ipfsOp
    async def update(self, ipfsop):
        pass

    @ipfsOp
    async def getRsaPubKey(self, op):
        return await self.ipid.pubKeyPemGet()

    async def watch(self):
        if self.peerUnresponsive:
            await self.sInactive.emit(self.peerId)
        else:
            ensureLater(120, self.watch)


class Peers:
    changed = AsyncSignal()
    peerAdded = AsyncSignal(str)
    peerModified = AsyncSignal(str)
    peerDidModified = AsyncSignal(str, bool)
    peerLogout = AsyncSignal(str)

    def __init__(self, ctx):
        self.app = QApplication.instance()
        self.ctx = ctx
        self.lock = asyncio.Lock(loop=self.app.loop)
        self.evStopWatcher = asyncio.Event()
        self._byPeerId = collections.OrderedDict()

    @property
    def byPeerId(self):
        return self._byPeerId

    @property
    def peersIds(self):
        return self.byPeerId.keys()

    @property
    def peersCount(self):
        return len(self.peersIds)

    @property
    def peersHandles(self):
        return [pCtx.ident.iphandle for peerId, pCtx in self.byPeerId.items()]

    async def unregister(self, peerId):
        with await self.lock:
            if peerId in self.byPeerId:
                del self.byPeerId[peerId]
            await self.peerLogout.emit(peerId)
            await self.changed.emit()

    @ipfsOp
    async def registerFromIdent(self, op, iMsg):
        # iMsg is a PeerIdentMessage

        if iMsg.peer not in self.byPeerId:
            peerValidated = False

            now = int(time.time())
            avgPing = await op.waitFor(op.pingAvg(iMsg.peer, count=2), 5)

            personDid = iMsg.personDid

            if not ipidFormatValid(personDid):
                log.debug('Invalid DID: {}'.format(personDid))
                return

            try:
                mType, stat = await self.app.rscAnalyzer(iMsg.iphandleqrpngcid)
            except Exception:
                log.debug('Invalid QR: {}'.format(iMsg.iphandleqrpngcid))
            else:
                statInfo = StatInfo(stat)

                if not statInfo.valid or statInfo.dataLargerThan(
                        kilobytes(128)) or not mType or not mType.isImage:
                    log.debug('Invalid stat for QR: {}'.format(
                        iMsg.iphandleqrpngcid))
                    return

                if not await self.validateQr(
                        iMsg.iphandleqrpngcid, iMsg) is True:
                    log.debug('Invalid QR: {}'.format(iMsg.iphandleqrpngcid))
                    peerValidated = False
                else:
                    log.debug('Ident QR {qr} for {peer} seems valid'.format(
                        qr=iMsg.iphandleqrpngcid, peer=iMsg.peer))
                    peerValidated = True

                ensure(op.pin(iMsg.iphandleqrpngcid))

            # Load the IPID
            ipid = await self.app.ipidManager.load(
                personDid,
                initialCid=iMsg.personDidCurCid,
                track=True
            )

            if not ipid:
                log.debug('Cannot load DID: {}'.format(personDid))
                return

            with await self.lock:
                pCtx = PeerCtx(self.ctx, iMsg.peer, iMsg, ipid,
                               pingavg=avgPing if avgPing else 0,
                               pinglast=now if avgPing else 0,
                               validated=peerValidated
                               )
                ipid.sChanged.connectTo(partialEnsure(
                    self.onPeerDidModified, pCtx))
                pCtx.sInactive.connectTo(self.onUnresponsivePeer)

                ensure(self.didPerformAuth(pCtx))

                self._byPeerId[iMsg.peer] = pCtx
                ensureLater(60, pCtx.watch)

            await self.peerAdded.emit(iMsg.peer)
        else:
            # This peer is already registered
            # What we ought to do here is just to refresh the DID document

            with await self.lock:
                pCtx = self.getByPeerId(iMsg.peer)
                if pCtx:
                    log.debug('Updating ident for peer {}'.format(iMsg.peer))
                    pCtx.ident = iMsg

                    log.debug('Refreshing DID: {}'.format(pCtx.ipid))
                    await pCtx.ipid.refresh()

                    await self.peerModified.emit(iMsg.peer)

        await self.changed.emit()

    @ipfsOp
    async def didPerformAuth(self, ipfsop, peerCtx):
        ipid = peerCtx.ipid

        if not ipid.local:
            # DID Auth
            for attempt in range(0, 3):
                log.debug('DID auth: {did} (attempt: {a})'.format(
                    did=ipid.did, a=attempt))
                if not await self.app.ipidManager.didAuthenticate(
                        ipid, peerCtx.ident.peer):
                    log.debug('DID auth failed for DID: {}'.format(ipid.did))
                    await ipfsop.sleep(5)
                    continue
                else:
                    log.debug('DID auth success for DID: {}'.format(ipid.did))
                    peerCtx._authenticated = True
                    break
        else:
            # We control this DID
            peerCtx._authenticated = True

    @ipfsOp
    async def validateQr(self, ipfsop, qrCid, iMsg):
        validCodes = 0
        try:
            codes = await self.app.rscAnalyzer.decodeQrCodes(qrCid)

            if not codes:
                # QR decoder not available, or invalid QR
                return False

            if len(codes) not in range(2, 4):
                return False

            for code in codes:
                if isinstance(code, IPFSPath):
                    if code.isIpns and str(code) == joinIpns(iMsg.peer):
                        validCodes += 1

                    if code.isIpfs:
                        computed = await ipfsop.hashComputeString(
                            iMsg.iphandle)

                        if computed['Hash'] == stripIpfs(code.objPath):
                            validCodes += 1
                elif isinstance(code, str) and ipidFormatValid(code) and \
                        code == iMsg.personDid:
                    validCodes += 1
        except Exception as e:
            log.debug('QR decode error: {}'.format(str(e)))
            return False
        else:
            # Just use 3 min codes here when we want the DID to be required
            return validCodes >= 2

        return False

    async def onPeerDidModified(self, peerCtx, didCid):
        log.debug('DID modified for peer: {}'.format(peerCtx.peerId))
        await self.peerDidModified.emit(peerCtx.peerId, True)

    async def onUnresponsivePeer(self, peerId):
        pCtx = self.getByPeerId(peerId)
        if pCtx:
            log.debug('{} unresponsive ..'.format(peerId))
            await self.unregister(peerId)

    async def init(self):
        pass

    async def stop(self):
        pass

    def getByPeerId(self, peerId):
        return self._byPeerId.get(peerId, None)

    def peerRegistered(self, peerId):
        return peerId in self.peersIds

    def __str__(self):
        return 'Galacteek peers registered: {0}'.format(self.peersCount)


class Node(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.ctx = parent
        self._id = None
        self._idFull = None

    @property
    def id(self):
        return self._id

    @property
    def idAll(self):
        return self._idFull

    @ipfsOp
    async def init(self, op):
        self._idFull = await op.client.core.id()
        self._id = await op.nodeId()


class PubsubMaster(QObject):
    psMessageRx = pyqtSignal()
    psMessageTx = pyqtSignal()

    chatRoomMessageReceived = pyqtSignal(ChatRoomMessage)

    def __init__(self, parent):
        super().__init__(parent)
        self.ctx = parent
        self._services = {}

    @property
    def services(self):
        return self._services

    def reg(self, service):
        self._services[service.topic] = service

    def status(self):
        [service.logStatus() for topic, service in self.services.items()]

    async def send(self, topic, message):
        if topic in self.services:
            await self.services[topic].send(str(message))

    async def stop(self):
        tsks = [service.stop() for topic, service in self.services.items()]
        return await asyncio.gather(*tsks)

    def startServices(self):
        [service.start() for topic, service in self.services.items()]

    @ipfsOp
    async def init(self, op):
        pass


class P2PServices(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.ctx = parent
        self._manager = tunnel.P2PTunnelsManager()
        self._services = []

    @property
    def tunnelsMgr(self):
        return self._manager

    @property
    def services(self):
        return self._services

    def servicesFormatted(self):
        return [{
            'name': srv.name,
            'descr': srv.description,
            'protocol': srv.protocolName
        } for srv in self.services]

    async def listeners(self):
        return await self._manager.getListeners()

    async def streamsAll(self):
        return await self._manager.streams()

    async def register(self, service):
        service.manager = self._manager
        self._services.append(service)

        await service.start()

    @ipfsOp
    async def init(self, op):
        from galacteek.ipfs.p2pservices import didauth

        if not await op.hasCommand('p2p') is True:
            log.debug('No P2P streams support')
            return

        log.debug('P2P streams support available')

        didAuthService = didauth.DIDAuthService()
        await self.register(didAuthService)

    async def stop(self):
        for srv in self.services:
            await srv.stop()


class IPFSContext(QObject):
    # signals
    ipfsConnectionReady = pyqtSignal()
    ipfsRepositoryReady = pyqtSignal()

    # profiles
    profilesAvailable = pyqtSignal(list)
    profileChanged = pyqtSignal(str, UserProfile)
    profileInfoAvailable = pyqtSignal()

    # log events
    logAddProvider = pyqtSignal(dict)

    # pubsub
    pubsubMessageRx = pyqtSignal()
    pubsubMessageTx = pyqtSignal()

    pubsubMarksReceived = pyqtSignal(int)

    # pinning signals
    pinQueueSizeChanged = pyqtSignal(int)
    pinItemStatusChanged = pyqtSignal(str, str, dict)
    pinItemRemoved = pyqtSignal(str, str)
    pinItemsCount = pyqtSignal(int)
    pinNewItem = pyqtSignal(str)
    pinFinished = pyqtSignal(str)

    def __init__(self, app):
        super().__init__()

        self._app = app

        self.objectStats = {}
        self.resources = {}
        self.profiles = {}
        self._currentProfile = None
        self.ipfsClient = None
        self._softIdent = None

        self.peers = Peers(self)
        self.node = Node(self)
        self.p2p = P2PServices(self)
        self.pubsub = PubsubMaster(self)

        self.pinner = None
        self.pinnerTask = None
        self.orbitConnector = None

    @property
    def app(self):
        return self._app

    @property
    def inOrbit(self):
        # We in orbit yet ?
        if self.orbitConnector:
            return self.orbitConnector.connected
        return False

    @property
    def loop(self):
        return self.app.loop

    @property
    def client(self):
        return self.ipfsClient

    @property
    def currentProfile(self):
        return self._currentProfile

    @currentProfile.setter
    def currentProfile(self, p):
        log.debug('Switched profile: {}'.format(p.name))
        self._currentProfile = p

    @property
    def rsaAgent(self):
        if self.currentProfile:
            return self.currentProfile.rsaAgent

    @property
    def softIdent(self):
        return self._softIdent

    @softIdent.setter
    def softIdent(self, ident):
        msg = 'Software ident changed to: CID {}'.format(ident['Hash'])
        log.debug(msg)
        logUser.info(msg)
        self._softIdent = ident

    def hasRsc(self, name):
        return name in self.resources

    @ipfsOp
    async def setup(self, ipfsop, pubsubEnable=True,
                    pubsubHashmarksExch=False, p2pEnable=True):
        self.rsaExec = RSAExecutor(loop=self.loop,
                                   executor=self.app.executor)
        await self.importSoftIdent()

        await self.node.init()
        await self.peers.init()

        if p2pEnable is True:
            await self.p2p.init()

        self.pinner = pinning.PinningMaster(
            self, statusFilePath=self.app.pinStatusLocation)
        await self.pinner.start()

        if pubsubEnable is True:
            self.setupPubsub(pubsubHashmarksExch=pubsubHashmarksExch)

    async def shutdown(self):
        if self.pinner:
            await self.pinner.stop()

        await self.peers.stop()
        await self.p2p.stop()
        await self.pubsub.stop()

    def setupPubsub(self, pubsubHashmarksExch=False):
        psServiceMain = PSMainService(self, self.app.ipfsClient)
        self.pubsub.reg(psServiceMain)

        psServicePeers = PSPeersService(self, self.app.ipfsClient)
        self.pubsub.reg(psServicePeers)

        psServiceChat = PSChatService(self, self.app.ipfsClient)
        self.pubsub.reg(psServiceChat)

        if pubsubHashmarksExch:
            psServiceMarks = PSHashmarksExchanger(
                self,
                self.app.ipfsClient,
                self.app.marksLocal,
                self.app.marksNetwork
            )
            self.pubsub.reg(psServiceMarks)

        self.pubsub.startServices()

    @ipfsOp
    async def profilesInit(self, ipfsop):
        hasGalacteek = await ipfsop.filesLookup('/', GALACTEEK_NAME)
        if not hasGalacteek:
            await ipfsop.client.files.mkdir(GFILES_ROOT_PATH, parents=True)

        rootList = await ipfsop.filesList(GFILES_ROOT_PATH)

        # Scans existing profiles
        for entry in rootList:
            name = entry['Name']
            if entry['Type'] == 1 and name.startswith('profile.'):
                ma = re.search(r'profile\.([a-zA-Z\.\_\-]*)$', name)
                if ma:
                    profileName = ma.group(1).rstrip()
                    await self.profileNew(profileName)

        defaultProfile = 'default'

        # Create default profile if not found
        if defaultProfile not in self.profiles:
            await self.profileNew(defaultProfile)

        self.profileEmitAvail()
        self.profileChange(defaultProfile)

    def profileGet(self, name):
        return self.profiles.get(name, None)

    def profileEmitAvail(self):
        self.loop.call_soon(self.profilesAvailable.emit,
                            list(self.profiles.keys()))

    async def profileNew(self, pName, emitavail=False):
        profile = UserProfile(self, pName, os.path.join(
            GFILES_ROOT_PATH, 'profile.{}'.format(pName)))
        try:
            await profile.init()
        except Exception as e:
            log.info('Could not initialize profile: {}'.format(
                str(e)), exc_info=True)
            return None
        self.profiles[pName] = profile
        if emitavail is True:
            self.profileEmitAvail()
        return profile

    def profileChange(self, pName):
        if pName in self.profiles:
            self.currentProfile = self.profiles[pName]
            self.profileChanged.emit(pName, self.currentProfile)
            return True
        else:
            return False

    @ipfsOp
    async def importSoftIdent(self, op):
        added = await op.addString(gSoftIdent)
        if added is not None:
            self.softIdent = added

    @ipfsOp
    async def galacteekPeers(self, op):
        if self.softIdent is not None:
            return await op.whoProvides(self.softIdent['Hash'])
        else:
            return []

    async def pin(self, path, recursive=False, callback=None, qname='default'):
        if self.pinner:
            await self.pinner.queue(path, recursive, callback, qname=qname)
