import asyncio
import aiorwlock
import re
import collections
import time
import os.path
from datetime import datetime

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QObject
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QPixmap

from galacteek import log
from galacteek import loopTime
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
from galacteek.ipfs.pubsub.messages.chat import ChatRoomMessage
from galacteek.ipfs.pubsub.service import PSMainService
from galacteek.ipfs.pubsub.srvs.chat import PSChatService
from galacteek.ipfs.pubsub.srvs.peers import PSPeersService
from galacteek.ipfs.pubsub.srvs.dagexchange import PSDAGExchangeService

from galacteek.ipfs.pubsub.messages.core import PeerIdentMessageV4

from galacteek.ipfs.ipfsops import *
from galacteek.ipfs import tunnel

from galacteek.core import utcDatetimeIso

from galacteek.did.ipid import ipidFormatValid
from galacteek.did.ipid import IPIdentifier

from galacteek.ui.helpers import getImageFromIpfs

from galacteek.core.profile import UserProfile
from galacteek.core.softident import gSoftIdent
from galacteek.core.iphandle import SpaceHandle

from galacteek.crypto.rsa import RSAExecutor
from galacteek.crypto.ecc import ECCExecutor


class PeerIdentityCtx:
    def __init__(self, ipfsCtx, peerId, ipHandle,
                 ipIdentifier: IPIdentifier,
                 pingavg=0,
                 validated=False,
                 authenticated=False):
        self._ipfsCtx = ipfsCtx
        self._ipid = ipIdentifier
        self.peerId = peerId
        self.iphandle = ipHandle
        self.pinghist = collections.deque([], 8)
        self._didPongLast = None
        self._identLast = int(time.time())
        self._validated = validated
        self._authenticated = authenticated
        self._identMsg = None

        self._avatarPath = None
        self._avatarImage = self.defaultAvatarImage()

        self._dtReg = datetime.now()
        self._processData = {}

        self.sInactive = AsyncSignal(str)
        self.sStatusChanged = AsyncSignal()

    @property
    def ipfsCtx(self):
        return self._ipfsCtx

    @property
    def ident(self):
        return self._identMsg

    @property
    def avatarImage(self):
        return self._avatarImage

    @property
    def avatarPath(self):
        return self._avatarPath

    @property
    def ipid(self):
        return self._ipid

    @property
    def didPong(self):
        return self._didPongLast

    @property
    def spaceHandle(self):
        return SpaceHandle(self.iphandle)

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
        self._identMsg = v
        self._identLast = int(time.time())

    def debug(self, msg):
        log.debug('Peer {p}@{ipid}: {msg}'.format(
            p=self.peerId, ipid=self.ipid.did, msg=msg))

    def alive(self):
        if self.ipid.local:
            return True

        try:
            prec = self.pinghist[-1]
            return int(loopTime()) - prec[1] < (60 * 5)
        except:
            return False

    def pingAvg(self):
        try:
            prec = self.pinghist[-1]
            return prec[0]
        except:
            return -1

    @ipfsOp
    async def update(self, ipfsop):
        pass

    @ipfsOp
    async def defaultRsaPubKey(self, ipfsop):
        if self.ident and isinstance(self.ident, PeerIdentMessageV4):
            return await ipfsop.catObject(self.ident.defaultRsaPubKeyCid)

    @ipfsOp
    async def pubKeyJwk(self, ipfsop):
        from jwcrypto import jwk

        rsaPubKey = await self.defaultRsaPubKey()
        if rsaPubKey:
            try:
                key = jwk.JWK()
                key.import_from_pem(rsaPubKey)
                return key
            except Exception as err:
                self.debug(f'Failed to load pub JWK: {err}')

    @ipfsOp
    async def getDidRsaPubKey(self, ipfsop):
        return await self.ipid.pubKeyPemGet()

    @ipfsOp
    async def watch(self, ipfsop):
        if self.ipid.local:
            self.pinghist.append((
                0,
                int(loopTime())
            ))
            return

        if self.ident is None:
            ensureLater(15, self.watch)
            return

        if isinstance(self.ident, PeerIdentMessageV4):
            idToken = self.ident.identToken

            pongReply = await ipfsop.waitFor(ipfsop.didPing(
                self.peerId, self.ipid.did,
                idToken), 30
            )

            self.debug(f'didping({self.ipid.did}) returned {pongReply}')

            if pongReply:
                ms, pong = pongReply
                if not pong:
                    # Retry later
                    ensureLater(30, self.watch)
                    return

                self._didPongLast = pong['didpong'][self.ipid.did]

                self.pinghist.append((
                    ms,
                    int(loopTime())
                ))

                ensureLater(140, self.watch)
                await self.sStatusChanged.emit()
            else:
                self.debug('Could not ping DID {self.ipid.did}')
                ensureLater(60, self.watch)

                await self.sStatusChanged.emit()
        else:
            return await self.watchOldStyle()

    @ipfsOp
    async def watchOldStyle(self, ipfsop):
        if self.ipid.local:
            self.pinghist.append((
                0,
                int(loopTime())
            ))
            return

        pingAvg = await ipfsop.waitFor(
            ipfsop.pingAvg(self.peerId, count=2), 10)

        if pingAvg and pingAvg > 0:
            self.pinghist.append((
                int(pingAvg),
                int(loopTime())
            ))

            self.debug(f'Ping OK: {pingAvg}')
            ensureLater(180, self.watch)

            await self.sStatusChanged.emit()
        else:
            self.debug('Could not ping peer')
            ensureLater(60, self.watch)

            await self.sStatusChanged.emit()

    def defaultAvatarImage(self):
        if isinstance(self.spaceHandle.vPlanet, str):
            image = QImage(
                ':/share/icons/planets/{planet}.png'.format(
                    planet=self.spaceHandle.vPlanet.lower()
                )
            )

            if not image.isNull():
                return image

        return QImage(':/share/icons/ipfs-cube-64.png')

    def avatarPixmapScaled(self, width=64, height=64):
        return QPixmap.fromImage(self.avatarImage).scaled(
            QSize(width, height),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

    @ipfsOp
    async def fetchAvatar(self, ipfsop):
        avatarServiceId = self.ipid.didUrl(path='/avatar')
        service = await self.ipid.searchServiceById(avatarServiceId)

        if service:
            avatarPath = IPFSPath(service.endpoint)

            if not avatarPath.valid:
                log.debug(f'Invalid avatar for peer {self.peerId}')

            self._avatarPath = avatarPath

            statInfo = StatInfo(
                await ipfsop.objStat(str(avatarPath),
                                     timeout=15)
            )

            if not statInfo.valid or statInfo.dataLargerThan(
                    kilobytes(768)):
                log.debug(f'Invalid avatar for peer {self.peerId}')
                return

            await ipfsop.ctx.pin(str(avatarPath), qname='ipid-avatar')

            log.debug(
                f'Getting avatar for peer {self.peerId} from {avatarPath}')

            image = await getImageFromIpfs(str(avatarPath))

            if image and not image.isNull():
                self._avatarImage = image
            else:
                log.debug(f'Could not fetch avatar for peer {self.peerId}')

    def __str__(self):
        return f'PeerIdentityCtx: handle {self.iphandle} ({self.ipid.did})'


class Peers:
    changed = AsyncSignal()
    peerAdded = AsyncSignal(PeerIdentityCtx)
    peerNew = AsyncSignal(PeerIdentityCtx)
    peerAuthenticated = AsyncSignal(PeerIdentityCtx)
    peerModified = AsyncSignal(PeerIdentityCtx)
    peerDidModified = AsyncSignal(PeerIdentityCtx, bool)

    # Unused now
    peerLogout = AsyncSignal(str)

    def __init__(self, ctx):
        self.app = QApplication.instance()
        self.ctx = ctx
        self.lock = aiorwlock.RWLock()
        self.evStopWatcher = asyncio.Event()
        self._byPeerId = collections.OrderedDict()
        self._byHandle = collections.OrderedDict()
        self._didGraphLStatus = []
        self._didAuthInp = {}
        self._pgScanCount = 0

        self.peerAuthenticated.connectTo(self.onPeerAuthenticated)

    @property
    def pgScanCount(self):
        return self._pgScanCount

    @property
    def byPeerId(self):
        return self._byPeerId

    @property
    def byHandle(self):
        return self._byHandle

    @property
    def peersIds(self):
        return self.byPeerId.keys()

    @property
    def peersCount(self):
        return len(self.peersHandles)

    @property
    def peersHandles(self):
        return [handle for handle in self.byHandle.keys()]

    async def onPeerLogout(self, peerId):
        # Not used anymore
        pass

    @ipfsOp
    async def watchNetworkGraph(self, ipfsop):
        profile = ipfsop.ctx.currentProfile

        # First scan
        await self.scanNetworkGraph()

        if profile.dagNetwork:
            profile.dagNetwork.dagUpdated.connectTo(self.networkGraphChanged)

    async def networkGraphChanged(self, dagCid):
        log.debug(
            f'Network graph moved to CID: {dagCid} '
            f'(graph scan run: {self.pgScanCount})'
        )

        await self.scanNetworkGraph()

    @ipfsOp
    async def scanNetworkGraph(self, ipfsop):
        profile = ipfsop.ctx.currentProfile

        async with profile.dagNetwork.read() as ng:
            for peerId, peerHandles in ng.d['peers'].items():
                for handle, hData in peerHandles.items():
                    sHandle = SpaceHandle(handle)
                    did = hData.get('did')

                    if peerId == ipfsop.ctx.node.id:
                        if did != profile.userInfo.personDid:
                            # Don't load inactive IPIDs
                            continue

                    log.debug(
                        f'scanNetworkGraph: processing {handle} ({did})')

                    if not sHandle.valid:
                        continue

                    # Is it in the model already ?
                    if self.app.peersTracker.model.didRegistered(did):
                        log.debug(f'DID {did}: already in model')
                        continue

                    if did in self._didGraphLStatus:
                        await ipfsop.sleep()
                        continue

                    ensure(
                        self.loadDidFromGraph(ipfsop, peerId, did, sHandle))
                    self._didGraphLStatus.append(did)

                    await ipfsop.sleep(0.1)

                await ipfsop.sleep(0.05)

        self._pgScanCount += 1

    async def loadDidFromGraph(self, ipfsop, peerId: str, did: str,
                               sHandle: str):
        for attempt in range(0, 8):
            ipid = await self.app.ipidManager.load(
                did,
                track=True,
                timeout=30,
                localIdentifier=(peerId == ipfsop.ctx.node.id)
            )

            if not ipid:
                log.debug(f'Cannot load IPID: {did}, attempt {attempt}')
                await ipfsop.sleep(60)
                continue
            else:
                break

        if not ipid:
            log.debug(f'Cannot load IPID: {did}, bailing out')
            self._didGraphLStatus.remove(did)
            return False

        piCtx = PeerIdentityCtx(
            self.ctx,
            sHandle.peer,
            str(sHandle),
            ipid,
            validated=True,
            authenticated=True
        )

        ipid.sChanged.connectTo(partialEnsure(
            self.onPeerDidModified, piCtx))
        piCtx.sStatusChanged.connectTo(partialEnsure(
            self.peerModified.emit, piCtx))

        ensureLater(1, piCtx.watch)

        async with self.lock.writer_lock:
            self._byHandle[str(sHandle)] = piCtx

            if piCtx.peerId not in self._byPeerId:
                self._byPeerId[piCtx.peerId] = piCtx

        log.debug(f'Loaded IPID from graph: {did}')

        await self.peerAdded.emit(piCtx)
        await ipfsop.sleep(1)

        self._didGraphLStatus.remove(did)

        return True

    @ipfsOp
    async def registerFromIdent(self, ipfsop, sender, iMsg):
        profile = ipfsop.ctx.currentProfile

        log.debug(f'registerFromIdent ({iMsg.peer}): '
                  f'DID: {iMsg.personDid}, handle: {iMsg.iphandle}')

        try:
            inGraph = await profile.dagNetwork.byDid(iMsg.personDid)
        except Exception:
            # network dag not ready ..
            log.debug(f'registerFromIdent {iMsg.personDid}: '
                      'network DAG not loaded yet ?')
            return

        if not inGraph:
            if isinstance(iMsg, PeerIdentMessageV4) and \
                    sender != ipfsop.ctx.node.id:
                pubKeyPem = await ipfsop.rsaPubKeyCheckImport(
                    iMsg.defaultRsaPubKeyCid)

                if not pubKeyPem:
                    log.debug(
                        f'Invalid RSA pub key .. {iMsg.defaultRsaPubKeyCid}')
                    return

                sigBlob = await ipfsop.catObject(iMsg.pssSigCurDid)
                if sigBlob is None:
                    log.debug(
                        f'Cannot get pss SIG {iMsg.pssSigCurDid}')
                    return

                if not await ipfsop.ctx.rsaExec.pssVerif(
                    iMsg.personDid.encode(),
                    sigBlob,
                    pubKeyPem
                ):
                    log.debug(f'Invalid PSS sig for peer {sender}')
                    return
                else:
                    log.debug(f'Valid PSS sig for {sender} !')

            peerValidated = False
            personDid = iMsg.personDid

            if not ipidFormatValid(personDid):
                log.debug('Invalid DID: {}'.format(personDid))
                return

            inProgress = self._didAuthInp.get(personDid, False)

            if inProgress is True:
                log.debug(f'registerFromIdent {iMsg.personDid}: '
                          f'authentication in progress')
                return

            self._didAuthInp[personDid] = True

            try:
                mType, stat = await self.app.rscAnalyzer(iMsg.iphandleqrpngcid)
            except Exception:
                log.debug('Invalid QR: {}'.format(iMsg.iphandleqrpngcid))
                self._didAuthInp[personDid] = False
                return
            else:
                statInfo = StatInfo(stat)

                if not statInfo.valid or statInfo.dataLargerThan(
                        kilobytes(512)) or not mType or not mType.isImage:
                    log.debug('Invalid stat for QR: {}'.format(
                        iMsg.iphandleqrpngcid))
                    self._didAuthInp[personDid] = False
                    return

                if not await self.validateQr(
                        iMsg.iphandleqrpngcid, iMsg) is True:
                    log.debug('Invalid QR: {}'.format(iMsg.iphandleqrpngcid))
                    peerValidated = False
                    self._didAuthInp[personDid] = False
                    return
                else:
                    log.debug('Ident QR {qr} for {peer} seems valid'.format(
                        qr=iMsg.iphandleqrpngcid, peer=iMsg.peer))
                    peerValidated = True

                await ipfsop.ctx.pin(iMsg.iphandleqrpngcid)

            # Load the IPID

            for attempt in range(0, 2):
                ipid = await self.app.ipidManager.load(
                    personDid,
                    localIdentifier=(iMsg.peer == ipfsop.ctx.node.id)
                )

                if ipid:
                    break

            if not ipid:
                log.debug(f'Cannot load DID: {personDid}')
                self._didAuthInp[personDid] = False
                return

            async with self.lock.writer_lock:
                piCtx = PeerIdentityCtx(
                    self.ctx, iMsg.peer, iMsg.iphandle,
                    ipid,
                    validated=peerValidated
                )

                ipid.sChanged.connectTo(partialEnsure(
                    self.onPeerDidModified, piCtx))
                piCtx.sStatusChanged.connectTo(partialEnsure(
                    self.peerModified.emit, piCtx))
                piCtx.ident = iMsg

                ensure(self.didPerformAuth(piCtx, iMsg))

                self._byHandle[iMsg.iphandle] = piCtx
                ensureLater(5, piCtx.watch)
        else:
            # This peer is already registered in the network graph
            # What we ought to do here is just to refresh the DID document

            async with self.lock.writer_lock:
                piCtx = self.getByHandle(iMsg.iphandle)

                if piCtx:
                    self._byPeerId[piCtx.peerId] = piCtx

                    log.debug('Updating ident for peer {}'.format(iMsg.peer))

                    piCtx.ident = iMsg

                    log.debug('Refreshing DID: {}'.format(piCtx.ipid))
                    await piCtx.ipid.refresh()

                    await self.peerModified.emit(piCtx)

        await self.changed.emit()

    @ipfsOp
    async def didPerformAuth(self, ipfsop, piCtx, identMsg):
        ipid = piCtx.ipid
        idToken = None

        if isinstance(identMsg, PeerIdentMessageV4):
            idToken = identMsg.identToken

        if not ipid.local:
            # DID Auth
            for attempt in range(0, 3):
                log.debug('DID auth: {did} (attempt: {a})'.format(
                    did=ipid.did, a=attempt))

                if not await self.app.ipidManager.didAuthenticate(
                        ipid, piCtx.peerId, token=idToken):
                    log.debug('DID auth failed for DID: {}'.format(ipid.did))
                    await ipfsop.sleep(5)
                    continue
                else:
                    log.debug('DID auth success for DID: {}'.format(ipid.did))
                    piCtx._authenticated = True

                    # Authenticated
                    await self.peerAuthenticated.emit(piCtx)

                    # Peering
                    await self.peeringAdd(piCtx)
                    break
        else:
            # We control this DID
            piCtx._authenticated = True
            await self.peerAuthenticated.emit(piCtx)

        self._didAuthInp[ipid.did] = False

    @ipfsOp
    async def onPeerAuthenticated(self, ipfsop, piCtx: PeerIdentityCtx):
        """
        DID auth was successfull for a peer, store the handle
        and DID in the graph, and create the initial IPLD
        link for the DID document (diddoc)
        """

        profile = ipfsop.ctx.currentProfile
        did = piCtx.ipid.did
        handle = str(piCtx.spaceHandle)

        async with profile.dagNetwork as g:
            pData = g.root['peers'].setdefault(piCtx.peerId, {})

            if handle in pData:
                # This handle is already registered for this peer
                # This can happen if a peer created 2 IPIDs with
                # the same handle after losing the profile's data

                log.debug(f'{handle} already in the graph, overwriting')

            pData[handle] = {
                'did': did,
                'diddoc': {},
                'dateregistered': utcDatetimeIso(),
                'datedidauth': utcDatetimeIso(),
                'datelastseen': utcDatetimeIso(),
                'flags': 0
            }

            # Link the DID document in the graph
            if piCtx.ipid.docCid:
                pData[handle]['diddoc'] = g.ipld(piCtx.ipid.docCid)

            log.debug(f'Authenticated {handle} ({did}) in the peers graph')

    async def peeringAdd(self, piCtx: PeerIdentityCtx):
        """
        Register the peer in go-ipfs Peering.Peers
        This way we make sure galacteek peers are always peered well
        """

        if self.app.ipfsd:
            await self.app.ipfsd.ipfsConfigPeeringAdd(piCtx.peerId)

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

    @ipfsOp
    async def onPeerDidModified(self, ipfsop, piCtx: PeerIdentityCtx,
                                didCid: str):
        log.debug('DID modified for peer: {}'.format(piCtx.peerId))

        profile = ipfsop.ctx.currentProfile
        await profile.dagNetwork.didUpdateObj(piCtx.ipid.did, didCid)

        await self.peerDidModified.emit(piCtx, True)

    async def onUnresponsivePeer(self, peerId):
        # Unused
        piCtx = self.getByPeerId(peerId)
        if piCtx:
            log.debug('{} unresponsive ..'.format(peerId))
            await self.unregister(peerId)

    async def init(self):
        pass

    async def stop(self):
        pass

    def getByPeerId(self, peerId):
        return self._byPeerId.get(peerId, None)

    def getByHandle(self, handle):
        return self._byHandle.get(handle, None)

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
    async def init(self, ipfsop):
        self._idFull = await ipfsop.client.core.id()
        self._id = await ipfsop.nodeId()


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

    def byTopic(self, topic):
        return self._services.get(topic)

    def status(self):
        [service.logStatus() for topic, service in self.services.items()]

    async def send(self, topic, message):
        if topic in self.services:
            await self.services[topic].send(str(message))

    async def stop(self):
        tsks = [service.stop() for topic, service in self.services.items()]
        return await asyncio.gather(*tsks)

    async def startServices(self):
        [await service.start() for topic, service in self.services.items()]

    @ipfsOp
    async def init(self, ipfsop):
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
    async def init(self, ipfsop):
        from galacteek.ipfs.p2pservices import didauth
        from galacteek.ipfs.p2pservices import dagexchange

        if not await ipfsop.hasCommand('p2p') is True:
            log.debug('No P2P streams support')
            return

        log.debug('P2P streams support available')

        try:
            self.didAuthService = didauth.DIDAuthService()
            await self.register(self.didAuthService)
        except Exception:
            log.debug('Could not register DID Auth service')

        try:
            self.dagExchService = dagexchange.DAGExchangeService()
            await self.register(self.dagExchService)
        except Exception:
            log.debug('Could not register DAG service')

    async def stop(self):
        for srv in self.services:
            await srv.stop()


class IPFSContext(QObject):
    # signals
    ipfsConnectionReady = AsyncSignal()
    ipfsRepositoryReady = AsyncSignal()

    _ipfsRepositoryReady = pyqtSignal()  # for pytest

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
        self._softIdent = ident

    def hasRsc(self, name):
        return name in self.resources

    @ipfsOp
    async def setup(self, ipfsop, pubsubEnable=True,
                    pubsubHashmarksExch=False, p2pEnable=True,
                    offline=False):
        self.rsaExec = RSAExecutor(loop=self.loop,
                                   executor=self.app.executor)
        self.eccExec = ECCExecutor(loop=self.loop,
                                   executor=self.app.executor)

        await self.importSoftIdent()
        await self.node.init()
        await self.peers.init()

        if p2pEnable is True and not offline:
            await self.p2p.init()

        self.pinner = pinning.PinningMaster(
            self, statusFilePath=self.app.pinStatusLocation)
        await self.pinner.start()

        if pubsubEnable is True and not offline:
            await self.setupPubsub(pubsubHashmarksExch=pubsubHashmarksExch)

    async def shutdown(self):
        if self.pinner:
            await self.pinner.stop()

        await self.peers.stop()
        await self.p2p.stop()
        await self.pubsub.stop()

    async def setupPubsub(self, pubsubHashmarksExch=False):
        psServiceMain = PSMainService(self, self.app.ipfsClient,
                                      scheduler=self.app.scheduler)
        self.pubsub.reg(psServiceMain)

        psServicePeers = PSPeersService(self, self.app.ipfsClient,
                                        scheduler=self.app.scheduler)
        self.pubsub.reg(psServicePeers)

        psServiceChat = PSChatService(self, self.app.ipfsClient,
                                      scheduler=self.app.scheduler)
        self.pubsub.reg(psServiceChat)

        self.pubsub.reg(
            PSDAGExchangeService(self, self.app.ipfsClient,
                                 scheduler=self.app.scheduler))

        await self.pubsub.startServices()

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
    async def importSoftIdent(self, ipfsop):
        added = await ipfsop.addString(gSoftIdent)
        if added is not None:
            self.softIdent = added

    @ipfsOp
    async def galacteekPeers(self, ipfsop):
        if self.softIdent is not None:
            return await ipfsop.whoProvides(self.softIdent['Hash'])
        else:
            return []

    async def pin(self, path, recursive=False, callback=None, qname='default'):
        if self.pinner:
            await self.pinner.queue(path, recursive, callback, qname=qname)
