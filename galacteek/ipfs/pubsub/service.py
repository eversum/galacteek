import orjson
import asyncio
import time
import collections
import traceback
import base64
from asyncio_throttle import Throttler

from galacteek import log as logger
from galacteek import AsyncSignal
from galacteek import ensureLater

from galacteek.ipfs.pubsub import TOPIC_MAIN
from galacteek.ipfs.pubsub import TOPIC_HASHMARKS
from galacteek.ipfs.pubsub import MsgAttributeRecordError

from galacteek.ipfs.pubsub.messages.core import PubsubMessage
from galacteek.ipfs.pubsub.messages.core import MarksBroadcastMessage

from galacteek.ipfs.wrappers import ipfsOp

from galacteek.core.asynclib import asyncify
from galacteek.core.asynclib import async_enterable
from galacteek.core.ipfsmarks import IPFSMarks

from galacteek.core.ps import keyPsJson
from galacteek.core.ps import keyPsEncJson
from galacteek.core.ps import psSubscriber
from galacteek.core.ps import gHub

from galacteek.database.psmanager import psManagerForTopic

import aioipfs


psServSubscriber = psSubscriber('pubsubServices')


class MsgSpy(object):
    def __init__(self, psDbManager, msgRecord, msgType, name, value):
        self.psDbManager = psDbManager
        self.msgType = msgType
        self.attrName = name
        self.value = value
        self.msgRecord = msgRecord

    async def __aenter__(self):
        entries = await self.psDbManager.searchMsgAttribute(
            self.msgType,
            self.attrName,
            self.value
        )
        self.found = len(entries) > 0

        if self.found:
            raise MsgAttributeRecordError(
                f'{self.msgType}: {self.attrName} exists')

        return self

    async def __aexit__(self, *args):
        if not self.found:
            self.rec = await self.psDbManager.recordMsgAttribute(
                self.msgRecord,
                self.msgType,
                self.attrName,
                self.value
            )


class PubsubService(object):
    """
    Generic IPFS pubsub service
    """

    hubPublish = True
    encodingType = 0

    def __init__(self, ipfsCtx, client, topic='galacteek.default',
                 runPeriodic=False, filterSelfMessages=True,
                 maxMsgTsDiff=None, minMsgTsDiff=None,
                 maxMessageSize=32768,
                 thrRateLimit=10,
                 thrPeriod=1.0,
                 thrRetry=0.5,
                 hubPublishDD=True,
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

        self.psDbManager = await psManagerForTopic(
            self.topic, encType=self.encodingType)

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

    async def gHubPublish(self, key, msg):
        gHub.publish(key, msg)
        await asyncio.sleep(0.5)

    @async_enterable
    async def msgSpy(self, dbRecord, msgType, attrName, value):
        return MsgSpy(
            self.psDbManager,
            dbRecord,
            msgType,
            attrName,
            value
        )


class JSONPubsubService(PubsubService):
    """
    JSON pubsub listener, handling incoming messages as JSON objects
    """

    encodingType = 1
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

                        rec = await self.psDbManager.recordMessage(
                            sender,
                            len(data['data']),
                            seqNo=data['seqno']
                        )

                        await self.processJsonMessage(
                            sender, msg,
                            msgDbRecord=rec
                        )
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

    async def processJsonMessage(self, sender, msg, msgDbRecord=None):
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

    async def processJsonMessage(self, sender, msg, msgDbRecord=None):
        if self.autoExpand:
            expanded = await self.expand(msg)
            if expanded:
                return await self.processLdMessage(sender, expanded)
        else:
            JSONPubsubService.processJsonMessage(
                self, sender, msg, msgDbRecord=msgDbRecord)

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

    async def processJsonMessage(self, sender, msg, msgDbRecord=None):
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


class RSAEncryptedJSONPubsubService(JSONPubsubService):
    encodingType = 2
    hubKey = keyPsEncJson

    def __init__(self, ipfsCtx, client, baseTopic, peered=True, **kw):
        self.baseTopic = baseTopic
        self.peered = peered

        kw.update(topic=self.peeredTopic(ipfsCtx.node.id))

        super().__init__(ipfsCtx, client, **kw)

    def peeredTopic(self, peerId):
        if self.peered:
            return f'{self.baseTopic}.{peerId}'
        else:
            return self.baseTopic

    @ipfsOp
    async def asyncMsgDataToJson(self, ipfsop, msg):
        try:
            dec = await ipfsop.rsaAgent.decrypt(
                base64.b64decode(msg['data']))
            return orjson.loads(dec.decode())
        except Exception as err:
            logger.debug(f'Could not decode encrypted message: {err}')
            return None

    async def peerEncFilter(self, piCtx, msg):
        return False

    async def peersToSend(self):
        # Yields (peerId, piCtx, aesSessionKey, topic)
        async with self.ipfsCtx.peers.lock.reader_lock:
            for peerId, piCtx in self.ipfsCtx.peers.byPeerId.items():
                yield (peerId, piCtx, None, None)

    @ipfsOp
    async def send(self, ipfsop, msg):
        async for peerId, piCtx, sessionKey, _topic in self.peersToSend():
            if await self.peerEncFilter(piCtx, msg) is True:
                continue

            topic = _topic if _topic else self.peeredTopic(peerId)

            pubKey = await piCtx.defaultRsaPubKey()

            if not pubKey:
                continue

            enc = await ipfsop.rsaAgent.encrypt(
                str(msg).encode(),
                pubKey,
                sessionKey=sessionKey,
                cacheKey=True
            )

            await ipfsop.sleep(0.05)

            if enc:
                await super().send(
                    base64.b64encode(enc).decode(),
                    topic=topic
                )

            await ipfsop.sleep(0.05)


class CurveJSONPubsubService(JSONPubsubService):
    encodingType = 3
    hubKey = keyPsEncJson

    def __init__(self, ipfsCtx, client, baseTopic, privEccKey,
                 peered=True, **kw):
        self.baseTopic = baseTopic
        self.peered = peered
        self.privEccKey = privEccKey

        kw.update(topic=self.peeredTopic(ipfsCtx.node.id))

        super().__init__(ipfsCtx, client, **kw)

    def peeredTopic(self, peerId):
        if self.peered:
            return f'{self.baseTopic}.{peerId}'
        else:
            return self.baseTopic

    @ipfsOp
    async def asyncMsgDataToJson(self, ipfsop, msg):
        try:
            sender = msg['from'] if isinstance(msg['from'], str) else \
                msg['from'].decode()
            piCtx = ipfsop.ctx.peers.getByPeerId(sender)
            if not piCtx:
                raise Exception('Cannot find peer')

            pubKey = await piCtx.defaultCurve25519PubKey()
            print(piCtx.peerId, 'ecc', pubKey)

            dec = await ipfsop.ctx.curve25Exec.decrypt(
                base64.b64decode(msg['data']),
                self.privEccKey,
                pubKey
            )
            return orjson.loads(dec.decode())
        except Exception as err:
            import traceback
            traceback.print_exc()
            logger.debug(f'Could not decode encrypted message: {err}')
            return None

    async def peerEncFilter(self, piCtx, msg):
        return False

    async def peersToSend(self):
        # Yields (peerId, piCtx, aesSessionKey, topic)
        async with self.ipfsCtx.peers.lock.reader_lock:
            for peerId, piCtx in self.ipfsCtx.peers.byPeerId.items():
                yield (peerId, piCtx, None, None)

    @ipfsOp
    async def send(self, ipfsop, msg):
        async for piCtx, sessionKey, _topic, pubKeyCid in self.peersToSend():
            if await self.peerEncFilter(piCtx, msg) is True:
                continue

            topic = _topic if _topic else self.peeredTopic(piCtx.peerId)

            pubKey = await ipfsop.catObject(pubKeyCid)

            if not pubKey:
                continue

            enc = await ipfsop.ctx.curve25Exec.encrypt(
                str(msg).encode(),
                self.privEccKey,
                pubKey
            )

            await ipfsop.sleep(0.05)

            if enc:
                await super().send(
                    base64.b64encode(enc).decode(),
                    topic=topic
                )

            await ipfsop.sleep(0.05)
