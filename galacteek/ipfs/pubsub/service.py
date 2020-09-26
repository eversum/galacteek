import orjson
import asyncio
import time
import collections
import traceback
import secrets
import async_timeout
import base64
from asyncio_throttle import Throttler

from galacteek import log as logger
from galacteek import AsyncSignal
from galacteek import ensureLater
from galacteek import ensure

from galacteek.ipfs.pubsub import TOPIC_MAIN
from galacteek.ipfs.pubsub import TOPIC_PEERS
from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek.ipfs.pubsub import TOPIC_ENC_CHAT
from galacteek.ipfs.pubsub import TOPIC_HASHMARKS
from galacteek.ipfs.pubsub import TOPIC_DAGEXCH

from galacteek.ipfs.pubsub.messages.core import PubsubMessage
from galacteek.ipfs.pubsub.messages.core import MarksBroadcastMessage
from galacteek.ipfs.pubsub.messages.core import PeerIdentMessageV3
from galacteek.ipfs.pubsub.messages.core import PeerIdentMessageV4
from galacteek.ipfs.pubsub.messages.core import PeerLogoutMessage
from galacteek.ipfs.pubsub.messages.core import PeerIpHandleChosen

from galacteek.ipfs.pubsub.messages.chat import ChatRoomMessage
from galacteek.ipfs.pubsub.messages.chat import ChatStatusMessage
from galacteek.ipfs.pubsub.messages.chat import ChatChannelsListMessage

from galacteek.ipfs.pubsub.messages.dagexch import DAGExchangeMessageV1

from galacteek.ipfs.wrappers import ipfsOp

from galacteek.core.asynclib import asyncify
from galacteek.core.asynclib import loopTime
from galacteek.core.ipfsmarks import IPFSMarks
from galacteek.core.ps import keyChatChannels
from galacteek.core.ps import keyPsJson
from galacteek.core.ps import keyPsEncJson
from galacteek.core.ps import keyTokensDagExchange
from galacteek.core.ps import keyTokensIdent
from galacteek.core.ps import keySnakeDagExchange
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
                 thrRateLimit=10,
                 thrPeriod=3.0,
                 thrRetry=1.0,
                 hubPublish=True,
                 scheduler=None):
        self.client = client
        self.ipfsCtx = ipfsCtx
        self.topic = topic
        self.inQueue = asyncio.Queue()
        self.errorsQueue = asyncio.Queue()
        self.lock = asyncio.Lock()
        self.scheduler = scheduler

        self._hubPublish = hubPublish
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

        self.throttler = Throttler(
            rate_limit=thrRateLimit,
            period=thrPeriod,
            retry_interval=thrRetry
        )

        self.addMessageFilter(self.filterMessageSize)
        self.addMessageFilter(self.filterPeerActivity)

        if filterSelfMessages is True:
            self.addMessageFilter(self.filterSelf)

    @property
    def hubPublish(self):
        return self._hubPublish

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
        ltime = self.client.loop.time()

        senderNodeId = msg['from'] if isinstance(msg['from'], str) else \
            msg['from'].decode()

        # Don't filter our messages
        if senderNodeId == self.ipfsCtx.node.id:
            return False

        if senderNodeId not in self._peerActivity:
            self._peerActivity[senderNodeId] = collections.deque([], 6)

        records = self._peerActivity[senderNodeId]
        records.appendleft((ltime, len(msg['data'])))

        if len(records) >= 2 and isinstance(self._minMsgTsDiff, int):
            latestIdx = len(records) - 1
            latest = records[latestIdx][0]
            previous = records[latestIdx - 1][0]

            latest = records[0][0]
            previous = records[1][0]

            if (latest - previous) < self._minMsgTsDiff:
                records.popleft()
                self.debug(f'Ignoring message from {senderNodeId}: '
                           f'Min TS diff {self._minMsgTsDiff} not reached')
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

    async def send(self, msg, topic=None):
        """
        Publish a message

        :param msg: message or message payload
        """

        if topic is None:
            topic = self.topic

        if issubclass(msg.__class__, PubsubMessage):
            data = str(msg)
        elif isinstance(msg, str):
            data = msg
        else:
            raise ValueError('Invalid message data')

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
    hubKey = keyPsJson

    def msgDataToJson(self, msg):
        """
        Decode JSON data contained in a pubsub message
        """
        try:
            return orjson.loads(msg['data'].decode())
        except Exception:
            logger.debug('Could not decode JSON message data')
            return None

    async def processMessages(self):
        try:
            asyncConv = getattr(self, 'asyncMsgDataToJson')
        except Exception:
            useAsyncConv = False
        else:
            useAsyncConv = asyncio.iscoroutinefunction(asyncConv)

        try:
            while True:
                async with self.throttler:
                    data = await self.inQueue.get()

                    if data is None:
                        continue

                    if useAsyncConv is True:
                        msg = await asyncConv(data)
                    else:
                        msg = self.msgDataToJson(data)

                    if msg is None:
                        self.debug('Invalid JSON message')
                        continue

                    sender = data['from'] if isinstance(
                        data['from'], str) else data['from'].decode()

                    try:
                        if self.hubPublish:
                            gHub.publish(
                                self.hubKey, (sender, self.topic, msg))

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
            self.debug(
                'Broadcast from unauthenticated peer: {0}'.format(sender))
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

        gHub.publish(keyTokensIdent, {'token': self.__identToken})

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


class PSChatService(JSONPubsubService):
    def __init__(self, ipfsCtx, client, **kw):
        super().__init__(ipfsCtx, client, topic=TOPIC_CHAT,
                         runPeriodic=True,
                         filterSelfMessages=True, **kw)

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unauthenticated peer: {}'.format(
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
    return f'{TOPIC_CHAT}.{channel}'


def encChatChannelTopic(channel):
    return f'{TOPIC_ENC_CHAT}.{channel}'


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
            self.debug('Message from unauthenticated peer: {}'.format(
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
        await asyncio.sleep(0.5)

    async def handleStatusMessage(self, sender, peerCtx, msg):
        sMsg = ChatStatusMessage(msg)
        if not sMsg.valid():
            self.debug('Invalid chat message')
            return

        sMsg.peerCtx = peerCtx
        gHub.publish(self.psKey, sMsg)
        await asyncio.sleep(0.5)


class EncryptedJSONPubsubService(JSONPubsubService):
    hubKey = keyPsEncJson

    def __init__(self, ipfsCtx, client, baseTopic, **kw):
        self.baseTopic = baseTopic
        kw.update(topic=self.peeredTopic(ipfsCtx.node.id))

        super().__init__(ipfsCtx, client, **kw, hubPublish=False)

    def peeredTopic(self, peerId):
        return f'{self.baseTopic}.{peerId}'

    @ipfsOp
    async def asyncMsgDataToJson(self, ipfsop, msg):
        try:
            dec = await ipfsop.rsaAgent.decrypt(
                base64.b64decode(msg['data']))
            return orjson.loads(dec.decode())
        except Exception as err:
            logger.debug(f'Could not decode encrypted message: {err}')
            return None

    def peerEncFilter(self, piCtx):
        return False

    @ipfsOp
    async def send(self, ipfsop, msg):
        async with self.ipfsCtx.peers.lock:
            for peerId, piCtx in self.ipfsCtx.peers.byPeerId.items():
                if self.peerEncFilter(piCtx) is True:
                    continue

                topic = self.peeredTopic(peerId)

                pubKey = await piCtx.defaultRsaPubKey()

                if not pubKey:
                    continue

                enc = await ipfsop.rsaAgent.encrypt(
                    str(msg).encode(),
                    pubKey
                )
                if enc:
                    await super().send(
                        base64.b64encode(enc).decode(),
                        topic=topic
                    )

                await ipfsop.sleep(0.1)


class PSDAGExchangeService(EncryptedJSONPubsubService):
    def __init__(self, ipfsCtx, client, **kw):
        super().__init__(ipfsCtx, client, TOPIC_DAGEXCH,
                         runPeriodic=True,
                         minMsgTsDiff=60,
                         thrRateLimit=8,
                         thrPeriod=20,
                         thrRetry=5,
                         filterSelfMessages=False, **kw)
        if 0:
            super().__init__(ipfsCtx, client,
                             topic=self.peeredTopic(ipfsCtx.node.id),
                             runPeriodic=True,
                             minMsgTsDiff=60,
                             thrRateLimit=8,
                             thrPeriod=20,
                             thrRetry=5,
                             filterSelfMessages=False, **kw)

        self.__authenticatedDags = collections.deque([], 128)
        self.__serviceToken = secrets.token_hex(64)

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unauthenticated peer: {}'.format(
                sender))
            return

        if msgType == DAGExchangeMessageV1.TYPE:
            await self.handleExchangeMessage(sender, msg)

    async def handleExchangeMessage(self, sender, msg):
        eMsg = DAGExchangeMessageV1(msg)
        if not eMsg.valid():
            self.debug('Invalid DAGExchange message')
            return

        if eMsg.dagClass == 'seeds':
            ensure(self.handleSeedsExchangeMessage(sender, eMsg))

    @ipfsOp
    async def _dagVerifyCidSignature(self, ipfsop, sender: str,
                                     dagCid: str,
                                     token: str,
                                     elixir: str,
                                     pubKeyPem):
        from aiohttp.web_exceptions import HTTPOk

        req = {
            'elixir': elixir,
            'sessiontoken': token
        }

        try:
            with async_timeout.timeout(40):
                async with ipfsop.p2pDialer(
                        sender, 'dagexchange',
                        addressAuto=True) as streamCtx:
                    if streamCtx.failed:
                        raise Exception(f'Cannot dial {sender}')

                    async with streamCtx.session.post(
                            streamCtx.httpUrl('/dagcidsign'),
                            json=req) as resp:
                        if resp.status != HTTPOk.status_code:
                            raise Exception(
                                f'DAG CID sign error {sender}: '
                                f'{resp.status}')

                        payload = await resp.json()
                        assert dagCid in payload

                        if await ipfsop.ctx.rsaExec.pssVerif64(
                                dagCid.encode(),
                                payload[dagCid]['pss64'].encode(),
                                pubKeyPem):
                            self.debug('DAG CID SIGN: {dagCid} OK!')
                            return True
                        else:
                            self.debug('DAG CID SIGN: {dagCid} Wrong!')
                            return False
        except asyncio.TimeoutError:
            self.debug(f'_dagVerifyCidSignature({dagCid}): timeout!')
            return False
        except Exception as err:
            self.debug(f'_dagVerifyCidSignature({dagCid}): error {err}')
            return False

    @ipfsOp
    async def handleSeedsExchangeMessage(self, ipfsop, sender, eMsg):
        profile = ipfsop.ctx.currentProfile
        local = (sender == ipfsop.ctx.node.id)

        if eMsg.dagNet == 'maindagnet':
            self.debug(f'Received seeds exchange message from {sender}')

            dag = profile.dagSeedsAll

            try:
                pubKeyPem = await ipfsop.rsaPubKeyCheckImport(
                    eMsg.signerPubKeyCid)

                if not pubKeyPem:
                    raise Exception(
                        'Could not load pub key for peer {sender}')

                if not local and eMsg.dagCid not in self.__authenticatedDags:
                    if not await self._dagVerifyCidSignature(
                        sender,
                        eMsg.dagCid,
                        eMsg.serviceToken,
                        eMsg.snakeOil[0:64],
                        pubKeyPem
                    ):
                        self.debug(f'DAG exchange: CID SIGWRONG {eMsg.dagCid}')
                        raise Exception(f'CID SIGWRONG {eMsg.dagCid}')
                    else:
                        self.__authenticatedDags.append(eMsg.dagCid)
                        self.debug(f'DAG exchange: CID SIGOK {eMsg.dagCid}')

                await dag.link(
                    sender, eMsg.dagUid, eMsg.dagCid,
                    eMsg.signerPubKeyCid,
                    local=local
                )
            except Exception as err:
                self.debug(f'Exception on DAG exchange: {err}')

            await ipfsop.sleep(3)

            if not local and eMsg.megaDagCid not in self.__authenticatedDags:
                if await self._dagVerifyCidSignature(
                    sender,
                    eMsg.megaDagCid,
                    eMsg.serviceToken,
                    eMsg.snakeOil[64:128],
                    pubKeyPem
                ):
                    self.debug(
                        f'DAG exchange: MCID SIGOK {eMsg.megaDagCid}')

                    # Do the merge
                    await dag.megaMerge(
                        sender, eMsg.megaDagCid,
                        eMsg.signerPubKeyCid,
                        local=local
                    )
                else:
                    self.debug(
                        f'DAG exchange: MCID SIGWRONG {eMsg.megaDagCid}')

    async def onSeedAdded(self, seedCid):
        await self.sendExchangeMessage()

    @ipfsOp
    async def sendExchangeMessage(self, ipfsop):
        self.debug('Sending seeds exchange message')

        seedsDag = ipfsop.ctx.currentProfile.dagSeedsMain
        seedsDagAll = ipfsop.ctx.currentProfile.dagSeedsAll

        oil = secrets.token_hex(64)

        gHub.publish(keyTokensDagExchange, {'token': self.__serviceToken})
        await ipfsop.sleep(0.5)

        gHub.publish(
            keySnakeDagExchange, {
                'snakeoil': oil,
                'cids': [
                    seedsDag.dagCid,
                    seedsDagAll.dagCid
                ],
                'expires': loopTime() + 180
            }
        )

        await ipfsop.sleep(0.5)

        pubKeyCid = await ipfsop.rsaAgent.pubKeyCid()

        eMsg = DAGExchangeMessageV1.make(
            seedsDag.dagClass,
            seedsDag.dagCid,
            seedsDag.dagNet,
            seedsDag.dagName,
            seedsDag.uid,
            pubKeyCid,
            seedsDagAll.dagCid,
            self.__serviceToken,
            oil
        )

        # TODO: rewrite that loop so that we don't hold the lock
        async with self.ipfsCtx.peers.lock:
            for peerId, piCtx in self.ipfsCtx.peers.byPeerId.items():
                topic = self.peeredTopic(peerId)

                pubKey = await piCtx.defaultRsaPubKey()

                if not pubKey:
                    continue

                enc = await ipfsop.rsaAgent.encrypt(
                    str(eMsg).encode(),
                    pubKey
                )
                if enc:
                    await self.send(
                        base64.b64encode(enc).decode(),
                        topic=topic
                    )

                await ipfsop.sleep(0.1)

        self.debug(f'DAGEXCH: Authorized DAGS: {self.__authenticatedDags}')

    @ipfsOp
    async def periodic(self, ipfsop):
        while True:
            if ipfsop.ctx.currentProfile:
                seedsDag = ipfsop.ctx.currentProfile.dagSeedsMain

                if seedsDag.dagUpdated.count() == 0:
                    # Sig not connected yet
                    seedsDag.dagUpdated.connectTo(self.onSeedAdded)

                await self.sendExchangeMessage()
                await asyncio.sleep(60 * 10)
            else:
                # Wait for the DAG
                await asyncio.sleep(5)


class PSEncryptedChatChannelService(EncryptedJSONPubsubService):
    def __init__(self, ipfsCtx, client, channel: str, psKey, **kw):
        self.psKey = psKey

        self._chatPeers = []

        super().__init__(ipfsCtx, client,
                         encChatChannelTopic(channel),
                         runPeriodic=True,
                         filterSelfMessages=False, **kw)

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unauthenticated peer: {}'.format(
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

        if cMsg.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_HEARTBEAT:
            await self.processHeartbeat(sender, cMsg)
        elif cMsg.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_JOINED:
            await self.processHeartbeat(sender, cMsg)
        elif cMsg.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_LEFT:
            self._chatPeers.remove(sender)

        gHub.publish(self.psKey, cMsg)
        await asyncio.sleep(0.5)

    def peerEncFilter(self, piCtx):
        if piCtx.peerId == self.ipfsCtx.node.id:
            return False

        return piCtx.peerId not in self._chatPeers

    async def processHeartbeat(self, sender, message):
        if sender not in self._chatPeers:
            self._chatPeers.append(sender)

    async def handleStatusMessage(self, sender, peerCtx, msg):
        sMsg = ChatStatusMessage(msg)
        if not sMsg.valid():
            self.debug('Invalid chat message')
            return

        sMsg.peerCtx = peerCtx
        gHub.publish(self.psKey, sMsg)
        await asyncio.sleep(0.5)
