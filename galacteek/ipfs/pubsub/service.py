import json

import asyncio
import time
import collections

from galacteek import log as logger

from galacteek.ipfs.pubsub import TOPIC_MAIN
from galacteek.ipfs.pubsub import TOPIC_PEERS
from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek.ipfs.pubsub import TOPIC_HASHMARKS

from galacteek.ipfs.pubsub.messages import MarksBroadcastMessage
from galacteek.ipfs.pubsub.messages import PeerIdentMessageV1
from galacteek.ipfs.pubsub.messages import PeerIdentMessageV2
from galacteek.ipfs.pubsub.messages import PeerLogoutMessage
from galacteek.ipfs.pubsub.messages import ChatRoomMessage

from galacteek.ipfs.wrappers import ipfsOp
from galacteek.core.asynclib import asyncify
from galacteek.core.ipfsmarks import IPFSMarks

import aioipfs


class PubsubService(object):
    """
    Generic IPFS pubsub service
    """

    def __init__(self, ipfsCtx, client, topic='galacteek.default',
                 runPeriodic=False, filterSelfMessages=True,
                 maxMsgTsDiff=None, minMsgTsDiff=None,
                 maxMessageSize=32768):
        self.client = client
        self.ipfsCtx = ipfsCtx
        self.topic = topic
        self.inQueue = asyncio.Queue()
        self.errorsQueue = asyncio.Queue()
        self.lock = asyncio.Lock()

        self._receivedCount = 0
        self._errorsCount = 0
        self._runPeriodic = runPeriodic
        self._filters = []
        self._peerActivity = {}
        self._maxMsgTsDiff = maxMsgTsDiff
        self._minMsgTsDiff = minMsgTsDiff
        self._maxMessageSize = maxMessageSize

        self.tskServe = None
        self.tskProcess = None
        self.tskPeriodic = None

        self.addMessageFilter(self.filterMessageSize)
        self.addMessageFilter(self.filterPeerActivity)

        if filterSelfMessages is True:
            self.addMessageFilter(self.filterSelf)

    @property
    def receivedCount(self):
        return self._receivedCount

    @property
    def errorsCount(self):
        return self._errorsCount

    @property
    def runPeriodic(self):
        return self._runPeriodic

    def debug(self, msg):
        logger.debug('PS[{0}]: {1}'.format(self.topic, msg))

    def logStatus(self):
        self.debug('** Messages received: {0}, errors: {1}'.format(
            self.receivedCount, self.errorsCount))

    def start(self):
        """ Create the different tasks for this service """
        self.tskServe = self.ipfsCtx.loop.create_task(self.serve())
        self.tskProcess = self.ipfsCtx.loop.create_task(self.processMessages())

        if self.runPeriodic:
            self.tskPeriodic = self.ipfsCtx.loop.create_task(self.periodic())

    async def stop(self):
        await self.shutdown()
        for tsk in [self.tskServe, self.tskProcess, self.tskPeriodic]:
            if not tsk:
                continue

            tsk.cancel()
            try:
                await tsk
            except asyncio.CancelledError as cErr:
                self.debug('task {task}: shutdown ERR: {err}'.format(
                    task=tsk, err=str(cErr)))
                continue
            else:
                self.debug('task {}: shutdown ok'.format(tsk))

    def addMessageFilter(self, filtercoro):
        if asyncio.iscoroutinefunction(filtercoro):
            self._filters.append(filtercoro)

    async def filterMessageSize(self, msg):
        if len(msg['data']) > self._maxMessageSize:
            return True
        return False

    async def filterPeerActivity(self, msg):
        senderNodeId = msg['from'].decode()
        if senderNodeId not in self._peerActivity:
            self._peerActivity[senderNodeId] = collections.deque([], 10)

        records = self._peerActivity[senderNodeId]
        records.append((time.time(), len(msg['data'])))

        if len(records) > 2 and isinstance(self._minMsgTsDiff, int):
            latestIdx = len(records) - 1
            latest = records[latestIdx][0]
            previous = records[latestIdx - 1][0]

            if (latest - previous) < self._minMsgTsDiff:
                return True

        return False

    async def filterSelf(self, msg):
        if msg['from'].decode() == self.ipfsCtx.node.id:
            return True

        return False

    async def filtered(self, message):
        for filter in self._filters:
            if await filter(message):  # That means we drop it
                return True
        return False

    async def shutdown(self):
        pass

    async def processMessages(self):
        """ Messages processing task to be implemented in your listener """
        return True

    async def periodic(self):
        return True

    async def serve(self):
        """
        Subscribe to the pubsub topic, read and filter incoming messages
        (dropping the ones emitted by us). Selected messages are put on the
        async queue (inQueue) to be later treated in the processMessages() task
        """

        try:
            async for message in self.client.pubsub.sub(self.topic):
                if await self.filtered(message):
                    continue

                self.ipfsCtx.pubsub.psMessageRx.emit()

                await self.inQueue.put(message)
                self._receivedCount += 1
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            self.debug('Cancelled, queue size was {0}'.format(
                self.inQueue.qsize()))
            return
        except Exception as e:
            self.debug('Serve interrupted by unknown exception {}'.format(
                str(e)))

    async def send(self, data, topic=None):
        """
        Publish a message

        :param str data: message payload
        """

        if topic is None:
            topic = self.topic

        try:
            status = await self.client.pubsub.pub(topic, data)
            self.ipfsCtx.pubsub.psMessageTx.emit()
        except aioipfs.APIError:
            logger.debug('Could not send pubsub message to {topic}'.format(
                topic=topic))
        else:
            return status


class JSONPubsubService(PubsubService):
    """
    JSON pubsub listener, handling incoming messages as JSON objects
    """

    def msgDataToJson(self, msg):
        """
        Decode JSON data contained in a pubsub message
        """
        try:
            return json.loads(msg['data'].decode())
        except Exception:
            logger.debug('Could not decode JSON message data')
            return None

    async def processMessages(self):
        try:
            while True:
                data = await self.inQueue.get()

                if data is None:
                    break

                msg = self.msgDataToJson(data)
                if msg is None:
                    continue

                try:
                    await self.processJsonMessage(data['from'].decode(), msg)
                except Exception as exc:
                    logger.debug(
                        'processJsonMessage error: {}'.format(str(exc)))
                    await self.errorsQueue.put((msg, exc))
                    self._errorsCount += 1
        except asyncio.CancelledError:
            return
        except Exception:
            return

    async def processJsonMessage(self, sender, msg):
        """ Implement this method to process incoming JSON messages"""
        return True


class PSHashmarksExchanger(JSONPubsubService):
    def __init__(self, ipfsCtx, client, marksLocal, marksNetwork):
        super().__init__(
            ipfsCtx,
            client,
            topic=TOPIC_HASHMARKS,
            runPeriodic=True,
            filterSelfMessages=True,
            maxMessageSize=131072,
            minMsgTsDiff=60 * 2)
        self.marksLocal = marksLocal
        self.marksNetwork = marksNetwork
        self.marksLocal.markAdded.connect(self.onMarkAdded)
        self._sendEvery = 60 * 8
        self._lastBroadcast = 0

    @property
    def curProfile(self):
        return self.ipfsCtx.currentProfile

    @asyncify
    async def onMarkAdded(self, path, mark):
        if mark['share'] is True:
            await self.broadcastSharedMarks()

    async def broadcastSharedMarks(self):
        try:
            sharedMarks = IPFSMarks(None, autosave=False)
            count = sharedMarks.merge(self.marksLocal, share=True, reset=True)

            if count > 0:
                self.debug('Sending shared hashmarks')
                msg = MarksBroadcastMessage.make(self.ipfsCtx.node.id,
                                                 sharedMarks.root)
                await self.send(str(msg))
                self._lastBroadcast = int(time.time())
        except BaseException:
            pass

    async def periodic(self):
        while True:
            await asyncio.sleep(self._sendEvery)
            await self.broadcastSharedMarks()

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)
        if msgType == MarksBroadcastMessage.TYPE:
            try:
                await self.processBroadcast(sender, msg)
            except BaseException:
                pass

    async def processBroadcast(self, sender, msg):
        bMsg = MarksBroadcastMessage(msg)

        if not bMsg.valid():
            self.debug('Invalid broadcast message')
            return

        if not self.ipfsCtx.peers.peerRegistered(sender):
            self.debug('Broadcast from unregistered peer: {0}'.format(sender))
            return

        marksJson = bMsg.marks
        if not marksJson:
            return

        marksCollection = IPFSMarks(None, data=marksJson, autosave=False)

        # JSON schema validation
        if not await marksCollection.isValidAsync():
            self.debug('Received invalid hashmarks from {sender}'.format(
                sender=sender))
            return
        else:
            self.debug('Hashmarks broadcast from {sender} is valid'.format(
                sender=sender))

        try:
            if self.curProfile:
                await self.curProfile.storeHashmarks(sender, marksCollection)
        except Exception:
            self.debug('Could not store data in hashmarks library')
        else:
            self.info('Stored hashmarks from peer: {0}'.format(sender))


class PSMainService(JSONPubsubService):
    def __init__(self, ipfsCtx, client):
        super().__init__(ipfsCtx, client, topic=TOPIC_MAIN)


class PSPeersService(JSONPubsubService):
    def __init__(self, ipfsCtx, client):
        super().__init__(ipfsCtx, client, topic=TOPIC_PEERS,
                         runPeriodic=True)

        self._curProfile = None
        self._identEvery = 45
        self.ipfsCtx.profileChanged.connect(self.onProfileChanged)

    @property
    def curProfile(self):
        return self.ipfsCtx.currentProfile

    @property
    def identEvery(self):
        return self._identEvery

    @asyncify
    async def onProfileChanged(self, pName, profile):
        await profile.userInfo.loaded

        try:
            profile.userInfo.entryChanged.disconnect(self.userInfoChanged)
            profile.userInfo.available.disconnect(self.userInfoAvail)
        except Exception:
            pass

        self.curProfile.userInfo.entryChanged.connect(self.userInfoChanged)
        self.curProfile.userInfo.available.connect(self.userInfoAvail)
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

        nodeId = op.ctx.node.id
        uInfo = profile.userInfo

        if not uInfo.valid():
            logger.debug('Profile info, ident message not sent')
            return

        cfgMaps = []

        if self.ipfsCtx.inOrbit:
            if profile.orbitalCfgMap:
                cfgMaps.append(profile.orbitalCfgMap.data)

        if uInfo.schemaVersion == 1:
            msg = PeerIdentMessageV2.make(
                nodeId,
                uInfo.objHash,
                uInfo.root,
                profile.dagUser.dagCid,
                profile.keyRootId,
                self.ipfsCtx.p2p.servicesFormatted(),
                cfgMaps
            )

            logger.debug('Sending ident message')
            await self.send(str(msg))
        else:
            logger.debug('Unknown schema version, ident message not sent')

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        if msgType == PeerIdentMessageV1.TYPE:
            logger.debug('Received ident message (v1) from {}'.format(sender))
            await self.handleIdentMessageV1(sender, msg)
        elif msgType == PeerIdentMessageV2.TYPE:
            logger.debug('Received ident message (v2) from {}'.format(sender))
            await self.handleIdentMessageV2(sender, msg)
        elif msgType == PeerLogoutMessage.TYPE:
            logger.debug('Received logout message from {}'.format(sender))
            await self.handleLogoutMessage(sender, msg)

        await asyncio.sleep(0)

    async def handleLogoutMessage(self, sender, msg):
        lMsg = PeerLogoutMessage(msg)
        if lMsg.valid():
            await self.ipfsCtx.peers.unregister(sender)

    async def handleIdentMessageV1(self, sender, msg):
        iMsg = PeerIdentMessageV1(msg)
        if not iMsg.valid():
            logger.debug('Received invalid ident message')
            return

        if sender != iMsg.peer:
            # You forging pubsub messages, son ?
            return

        await self.ipfsCtx.peers.registerFromIdent(iMsg)

    async def handleIdentMessageV2(self, sender, msg):
        iMsg = PeerIdentMessageV2(msg)
        if not iMsg.valid():
            logger.debug('Received invalid ident message')
            return

        if sender != iMsg.peer:
            # You forging pubsub messages, son ?
            return

        await self.ipfsCtx.peers.registerFromIdent(iMsg)

    @ipfsOp
    async def shutdown(self, op):
        msg = PeerLogoutMessage.make(op.ctx.node.id)
        await self.send(str(msg))

    async def periodic(self):
        while True:
            await asyncio.sleep(self.identEvery)

            with await self.lock:
                if self.curProfile:
                    await self.sendIdent(self.curProfile)


class PSChatService(JSONPubsubService):
    def __init__(self, ipfsCtx, client):
        super().__init__(ipfsCtx, client, topic=TOPIC_CHAT,
                         filterSelfMessages=False)

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        if msgType == ChatRoomMessage.TYPE:
            await self.handleChatMessage(msg)

    async def handleChatMessage(self, msg):
        cMsg = ChatRoomMessage(msg)
        if not cMsg.valid():
            return

        self.ipfsCtx.pubsub.chatRoomMessageReceived.emit(cMsg)


__all__ = [
    'PubsubService',
    'PSHashmarksExchanger',
    'PSMainService',
    'PSChatService',
    'PSPeersService'
]
