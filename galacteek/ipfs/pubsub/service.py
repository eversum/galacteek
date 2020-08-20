import json

import asyncio
import time
import collections
import traceback

from galacteek import log as logger
from galacteek import AsyncSignal
from galacteek import ensureLater

from galacteek.ipfs.pubsub import TOPIC_MAIN
from galacteek.ipfs.pubsub import TOPIC_PEERS
from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek.ipfs.pubsub import TOPIC_HASHMARKS

from galacteek.ipfs.pubsub.messages.core import MarksBroadcastMessage
from galacteek.ipfs.pubsub.messages.core import PeerIdentMessageV3
from galacteek.ipfs.pubsub.messages.core import PeerLogoutMessage
from galacteek.ipfs.pubsub.messages.core import PeerIpHandleChosen

from galacteek.ipfs.pubsub.messages.chat import ChatRoomMessage
from galacteek.ipfs.pubsub.messages.chat import ChatStatusMessage
from galacteek.ipfs.pubsub.messages.chat import ChatChannelsListMessage

from galacteek.ipfs.wrappers import ipfsOp

from galacteek.core.asynclib import asyncify
from galacteek.core.ipfsmarks import IPFSMarks
from galacteek.core.ps import keyChatChannels
from galacteek.core.ps import keyPsJson
from galacteek.core.ps import gHub

import aioipfs


class PubsubService(object):
    """
    Generic IPFS pubsub service
    """

    def __init__(self, ipfsCtx, client, topic='galacteek.default',
                 runPeriodic=False, filterSelfMessages=True,
                 maxMsgTsDiff=None, minMsgTsDiff=None,
                 maxMessageSize=32768,
                 scheduler=None):
        self.client = client
        self.ipfsCtx = ipfsCtx
        self.topic = topic
        self.inQueue = asyncio.Queue()
        self.errorsQueue = asyncio.Queue()
        self.lock = asyncio.Lock()
        self.scheduler = scheduler

        self._receivedCount = 0
        self._errorsCount = 0
        self._runPeriodic = runPeriodic
        self._filters = []
        self._peerActivity = {}
        self._maxMsgTsDiff = maxMsgTsDiff
        self._minMsgTsDiff = minMsgTsDiff
        self._maxMessageSize = maxMessageSize

        # Async sigs
        self.rawMessageReceived = AsyncSignal(str, str, bytes)
        self.rawMessageSent = AsyncSignal(str, str, str)

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

    def info(self, msg):
        logger.info('PS[{0}]: {1}'.format(self.topic, msg))

    def logStatus(self):
        self.debug('** Messages received: {0}, errors: {1}'.format(
            self.receivedCount, self.errorsCount))

    async def start(self):
        """ Create the different tasks for this service """

        if self.scheduler is None:
            raise Exception('No scheduler specified')

        self.tskServe = await self.scheduler.spawn(self.serve())
        self.tskProcess = await self.scheduler.spawn(self.processMessages())

        if self.runPeriodic:
            self.tskPeriodic = await self.scheduler.spawn(self.periodic())

    async def stop(self):
        await self.shutdown()

        for tsk in [self.tskServe, self.tskProcess, self.tskPeriodic]:
            if not tsk:
                continue

            try:
                await tsk.close()
            except asyncio.TimeoutError as tErr:
                self.debug(
                    'timeout while closing {task}: shutdown ERR: {err}'.format(
                        task=tsk, err=str(tErr)))
                continue
            except Exception as cErr:
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
        senderNodeId = msg['from'] if isinstance(msg['from'], str) else \
            msg['from'].decode()
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
        sender = msg['from'] if isinstance(msg['from'], str) else \
            msg['from'].decode()

        if sender == self.ipfsCtx.node.id:
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
                sender = message['from'] if isinstance(
                    message['from'], str) else message['from'].decode()

                await self.rawMessageReceived.emit(
                    self.topic, sender, message['data'])

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
            traceback.print_exc()
            self.debug('Serve interrupted by unknown exception {}'.format(
                str(e)))
            ensureLater(10, self.serve)

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

    jsonMessageReceived = AsyncSignal(str, str, bytes)

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
                    continue

                msg = self.msgDataToJson(data)
                if msg is None:
                    self.debug('Invalid JSON message')
                    continue

                sender = data['from'] if isinstance(data['from'], str) else \
                    data['from'].decode()

                try:
                    gHub.publish(keyPsJson, (sender, self.topic, msg))
                    await self.processJsonMessage(sender, msg)
                except Exception as exc:
                    self.debug(
                        'processJsonMessage error: {}'.format(str(exc)))
                    traceback.print_exc()
                    await self.errorsQueue.put((msg, exc))
                    self._errorsCount += 1
        except asyncio.CancelledError:
            self.debug('JSON process cancelled')
        except Exception as err:
            self.debug('JSON process exception: {}'.format(
                str(err)))

    async def processJsonMessage(self, sender, msg):
        """ Implement this method to process incoming JSON messages"""
        return True


class JSONLDPubsubService(JSONPubsubService):
    """
    JSON-LD pubsub listener, handling incoming messages as JSON-LD
    """

    def __init__(self, *args, autoExpand=False, **kw):
        super().__init__(*args, **kw)

        self.autoExpand = autoExpand

    @ipfsOp
    async def expand(self, ipfsop, data):
        try:
            async with ipfsop.ldOps() as ld:
                return await ld.expandDocument(data)
        except Exception:
            pass

    async def processJsonMessage(self, sender, msg):
        if self.autoExpand:
            expanded = await self.expand(msg)
            if expanded:
                return await self.processLdMessage(sender, expanded)
        else:
            JSONPubsubService.processJsonMessage(self, sender, msg)

    async def processLdMessage(self, sender, msg):
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
    def __init__(self, ipfsCtx, client, **kw):
        super().__init__(ipfsCtx, client, topic=TOPIC_MAIN, **kw)


class PSPeersService(JSONPubsubService):
    def __init__(self, ipfsCtx, client, **kw):
        super().__init__(ipfsCtx, client, topic=TOPIC_PEERS,
                         runPeriodic=True,
                         filterSelfMessages=False, **kw)

        self._curProfile = None
        self._identEvery = 25
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

        msg = await PeerIdentMessageV3.make(
            nodeId,
            profile.dagUser.dagCid,
            profile.keyRootId,
            uInfo,
            profile.userInfo.personDid,
            ipid.docCid
        )

        logger.debug('Sending ident message')
        await self.send(str(msg))

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        if msgType == PeerIdentMessageV3.TYPE:
            logger.debug('Received ident message (v3) from {}'.format(sender))
            await self.handleIdentMessageV3(sender, msg)
        elif msgType == PeerLogoutMessage.TYPE:
            logger.debug('Received logout message from {}'.format(sender))
            await self.handleLogoutMessage(sender, msg)
        elif msgType == PeerIpHandleChosen.TYPE:
            logger.debug('Received iphandle message from {}'.format(sender))
            await self.handleIpHandleMessage(sender, msg)

        await asyncio.sleep(0)

    @ipfsOp
    async def handleIpHandleMessage(self, ipfsop, sender, msg):
        profile = ipfsop.ctx.currentProfile

        iMsg = PeerIpHandleChosen(msg)
        if iMsg.valid():
            self.info('Welcoming {} to the network!'.format(iMsg.iphandle))
            await ipfsop.addString(iMsg.iphandle)
            await profile.ipHandles.register(iMsg.iphandle)

    async def handleLogoutMessage(self, sender, msg):
        lMsg = PeerLogoutMessage(msg)
        if lMsg.valid():
            await self.ipfsCtx.peers.unregister(sender)

    async def handleIdentMessageV3(self, sender, msg):
        iMsg = PeerIdentMessageV3(msg)
        if not iMsg.valid():
            logger.debug('Received invalid ident message')
            return

        if sender != iMsg.peer:
            # You forging pubsub messages, son ?
            return

        try:
            await self.ipfsCtx.peers.registerFromIdent(iMsg)
        except Exception as e:
            logger.debug('Registering from indent failed for peer: {}'.format(
                sender))
            raise e

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


class PSChatService(JSONPubsubService):
    def __init__(self, ipfsCtx, client, **kw):
        super().__init__(ipfsCtx, client, topic=TOPIC_CHAT,
                         runPeriodic=True,
                         filterSelfMessages=True, **kw)

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unregistered peer: {}'.format(
                sender))
            return

        if msgType == ChatChannelsListMessage.TYPE:
            await self.handleChannelsListMessage(msg)

    @ipfsOp
    async def handleChannelsListMessage(self, ipfsop, msg):
        cMsg = ChatChannelsListMessage(msg)
        if not cMsg.valid():
            self.debug('Invalid channels message')
            return

        self.debug('Received valid chat channels list message')

        # Publish to the hub
        gHub.publish(keyChatChannels, cMsg)

    @ipfsOp
    async def periodic(self, ipfsop):
        while True:
            await asyncio.sleep(90)

            if ipfsop.ctx.currentProfile:
                channelsDag = ipfsop.ctx.currentProfile.dagChatChannels

                await self.send(
                    ChatChannelsListMessage.make(channelsDag.channelsSorted)
                )


def chatChannelTopic(channel):
    return 'galacteek.chat.channels.{}'.format(channel)


class PSChatChannelService(JSONLDPubsubService):
    def __init__(self, ipfsCtx, client, channel: str, psKey,
                 **kw):

        topic = chatChannelTopic(channel)
        self.psKey = psKey

        super().__init__(ipfsCtx, client, topic=topic,
                         filterSelfMessages=False, **kw)

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unregistered peer: {}'.format(
                sender))
            return

        if msgType == ChatRoomMessage.TYPE:
            await self.handleChatMessage(sender, peerCtx, msg)

    async def handleChatMessage(self, sender, peerCtx, msg):
        cMsg = ChatRoomMessage(msg)
        if not cMsg.valid():
            self.debug('Invalid chat message')
            return

        cMsg.peerCtx = peerCtx
        gHub.publish(self.psKey, cMsg)

    async def handleStatusMessage(self, sender, peerCtx, msg):
        sMsg = ChatStatusMessage(msg)
        if not sMsg.valid():
            self.debug('Invalid chat message')
            return

        sMsg.peerCtx = peerCtx
        gHub.publish(self.psKey, sMsg)
