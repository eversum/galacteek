
import asyncio
import secrets

from galacteek import log as logger
from galacteek import ensure

from galacteek.core.asynclib import asyncify
from galacteek.core.ps import keyTokensIdent

from galacteek.ipfs import ipfsOp
from galacteek.ipfs.pubsub import TOPIC_PEERS
from galacteek.ipfs.pubsub.messages.core import PeerIdentMessageV3
from galacteek.ipfs.pubsub.messages.core import PeerIdentMessageV4
from galacteek.ipfs.pubsub.messages.core import PeerLogoutMessage
from galacteek.ipfs.pubsub.messages.core import PeerIpHandleChosen

from galacteek.ipfs.pubsub.service import JSONPubsubService


class PSPeersService(JSONPubsubService):
    def __init__(self, ipfsCtx, client, **kw):
        super().__init__(ipfsCtx, client, topic=TOPIC_PEERS,
                         runPeriodic=True,
                         minMsgTsDiff=30,
                         filterSelfMessages=False, **kw)

        self._curProfile = None
        self._identEvery = 60
        self.ipfsCtx.profileChanged.connect(self.onProfileChanged)
        self.__identToken = secrets.token_hex(64)

    @property
    def curProfile(self):
        return self.ipfsCtx.currentProfile

    @property
    def identEvery(self):
        return self._identEvery

    @asyncify
    async def onProfileChanged(self, pName, profile):
        await profile.userInfo.loaded
        await self.sendIdent(self.curProfile)

    @asyncify
    async def userInfoAvail(self, arg):
        await self.sendIdent(self.curProfile)

    @asyncify
    async def userInfoChanged(self):
        with await self.lock:
            await self.sendIdent(self.curProfile)

    @ipfsOp
    async def sendIdent(self, op, profile):
        if not profile.initialized:
            logger.debug('Profile not initialized, ident message not sent')
            return

        await self.gHubPublish(keyTokensIdent, {'token': self.__identToken})

        nodeId = op.ctx.node.id
        uInfo = profile.userInfo

        ipid = await op.ipidManager.load(
            profile.userInfo.personDid,
            localIdentifier=True
        )

        if not ipid:
            logger.info('Failed to load local DID')
            return
        else:
            logger.debug('Local IPID ({did}) load: OK, dagCID is {cid}'.format(
                did=profile.userInfo.personDid, cid=ipid.docCid))

        pssSigCurDid = await op.rsaAgent.pssSignImport(
            profile.userInfo.personDid.encode()
        )

        msg = await PeerIdentMessageV4.make(
            nodeId,
            self.__identToken,
            profile.dagUser.dagCid,
            profile.keyRootId,
            uInfo,
            profile.userInfo.personDid,
            ipid.docCid,
            await op.rsaAgent.pubKeyCid(),
            pssSigCurDid,
            profile.dagNetwork.dagCid
        )

        logger.debug('Sending ident message')
        await self.send(str(msg))

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        if msgType == PeerIdentMessageV3.TYPE:
            logger.debug('Received ident message (v3) from {}'.format(sender))
            await self.handleIdentMessageV3(sender, msg)
        if msgType == PeerIdentMessageV4.TYPE:
            logger.debug('Received ident message (v4) from {}'.format(sender))
            await self.handleIdentMessageV4(sender, msg)
        elif msgType == PeerLogoutMessage.TYPE:
            logger.debug('Received logout message from {}'.format(sender))
        elif msgType == PeerIpHandleChosen.TYPE:
            logger.debug('Received iphandle message from {}'.format(sender))
            await self.handleIpHandleMessage(sender, msg)

        await asyncio.sleep(0)

    @ipfsOp
    async def handleIpHandleMessage(self, ipfsop, sender, msg):
        iMsg = PeerIpHandleChosen(msg)
        if iMsg.valid():
            self.info('Welcoming {} to the network!'.format(iMsg.iphandle))
            await ipfsop.addString(iMsg.iphandle)

    async def handleLogoutMessage(self, sender, msg):
        lMsg = PeerLogoutMessage(msg)
        if lMsg.valid():
            await self.ipfsCtx.peers.onPeerLogout(sender)

    async def handleIdentMessageV3(self, sender, msg):
        iMsg = PeerIdentMessageV3(msg)
        if not iMsg.valid():
            logger.debug('Received invalid ident message')
            return

        if sender != iMsg.peer:
            # You forging pubsub messages, son ?
            return

        ensure(self.ipfsCtx.peers.registerFromIdent(sender, iMsg))

    async def handleIdentMessageV4(self, sender, msg):
        iMsg = PeerIdentMessageV4(msg)
        if not iMsg.valid():
            logger.debug('Received invalid ident message')
            return

        if sender != iMsg.peer:
            # You forging pubsub messages, son ?
            return

        ensure(self.ipfsCtx.peers.registerFromIdent(sender, iMsg))

    @ipfsOp
    async def sendLogoutMessage(self, ipfsop):
        msg = PeerLogoutMessage.make(ipfsop.ctx.node.id)
        await self.send(str(msg))

    async def shutdown(self):
        await self.sendLogoutMessage()

    async def periodic(self):
        while True:
            await asyncio.sleep(self.identEvery)

            with await self.lock:
                if self.curProfile:
                    await self.sendIdent(self.curProfile)
