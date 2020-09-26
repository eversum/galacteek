import asyncio
import aiorwlock
import orjson

from galacteek import log
from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek.ipfs.pubsub import TOPIC_ENC_CHAT

from galacteek.ipfs.pubsub.service import JSONPubsubService
from galacteek.ipfs.pubsub.service import RSAEncryptedJSONPubsubService

from galacteek.ipfs.pubsub.messages.chat import ChatRoomMessage
from galacteek.ipfs.pubsub.messages.chat import ChatStatusMessage
from galacteek.ipfs.pubsub.messages.chat import ChatChannelsListMessage
from galacteek.ipfs.pubsub.messages.chat import UserChannelsListMessage
from galacteek.ipfs.wrappers import ipfsOp

from galacteek.core.asynclib import loopTime
from galacteek.core.ps import keyChatChannels
from galacteek.core.ps import keyChatChanList
from galacteek.core.ps import keyChatChanUserList
from galacteek.core.ps import mSubscriber


def encChatChannelTopic(channel):
    return f'{TOPIC_ENC_CHAT}.{channel}'


def chatChannelTopic(channel):
    return f'{TOPIC_CHAT}.{channel}'


class PSChatService(JSONPubsubService):
    def __init__(self, ipfsCtx, client, **kw):
        super().__init__(ipfsCtx, client, topic=TOPIC_CHAT,
                         runPeriodic=True,
                         filterSelfMessages=False, **kw)
        self.lock = aiorwlock.RWLock()
        mSubscriber.add_async_listener(
            keyChatChanList, self.onUserChannelList)

        self.chanUsers = {}

    async def peersByChannel(self, channel):
        async with self.lock.reader_lock:
            for peer, data in self.chanUsers.items():
                if channel not in data:
                    continue

                yield peer, data[channel]['sessionkey']

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unauthenticated peer: {}'.format(
                sender))
            return

        if msgType == ChatChannelsListMessage.TYPE:
            await self.handleChannelsListMessage(msg)

        elif msgType == UserChannelsListMessage.TYPE:
            await self.handleUserChannelsMessage(sender, msg)

    @ipfsOp
    async def onUserChannelList(self, ipfsop, key, msg):
        await self.send(msg)

    async def chatChanUserListPub(self, chan):
        pList = [p async for p, _ in self.peersByChannel(chan)]

        await self.gHubPublish(
            keyChatChanUserList,
            (chan, pList)
        )

    @ipfsOp
    async def handleUserChannelsMessage(self, ipfsop, sender, msg):
        cMsg = UserChannelsListMessage(msg)
        if not cMsg.valid():
            return

        senderChans = cMsg.channels if cMsg.channels else []
        senderChans = cMsg.channels if cMsg.channels else {}

        pChans = self.chanUsers.setdefault(sender, {})
        for chan in pChans:
            if chan not in senderChans:
                async with self.lock.writer_lock:
                    del pChans[chan]

                await self.chatChanUserListPub(chan)

        def regChan(pCList, channel):
            pCList[channel] = {
                'dtreg': loopTime(),
                'sessionkey': ipfsop.ctx.rsaExec.randBytes()
            }

        for chan, chanData in senderChans.items():
            print(chan, chanData)

            if chan not in pChans:
                jwt = chanData.get('sessionjwt')

                if not jwt:
                    continue

                if ipfsop.ourNode(sender):
                    async with self.lock.writer_lock:
                        regChan(pChans, chan)
                else:
                    piCtx = ipfsop.ctx.peers.getByPeerId(sender)
                    baseTopic = encChatChannelTopic(chan)
                    topic = f'{baseTopic}.{sender}'
                    psPeers = await ipfsop.pubsubPeers(topic=topic, timeout=3)

                    if psPeers and len(psPeers) > 0:
                        pubJwk = await piCtx.pubKeyJwk()
                        payload = ipfsop.ctx.rsaExec.jwsVerify(
                            orjson.dumps(jwt).decode(),
                            pubJwk
                        )
                        if not payload:
                            continue

                        decoded = payload.decode()
                        if decoded == chan:
                            log.debug(f'Peer {sender}: valid JWS')
                        else:
                            log.debug(f'Peer {sender}: invalid JWS')
                            continue

                        async with self.lock.writer_lock:
                            regChan(pChans, chan)

                await self.chatChanUserListPub(chan)

            await ipfsop.sleep()

        log.debug(f'Peer {sender} chat channels: {pChans}')

    @ipfsOp
    async def handleChannelsListMessage(self, ipfsop, msg):
        cMsg = ChatChannelsListMessage(msg)
        if not cMsg.valid():
            self.debug('Invalid channels message')
            return

        self.debug('Received valid chat channels list message')

        # Publish to the hub
        await self.gHubPublish(keyChatChannels, cMsg)

    @ipfsOp
    async def periodic(self, ipfsop):
        while True:
            await asyncio.sleep(90)

            if ipfsop.ctx.currentProfile:
                channelsDag = ipfsop.ctx.currentProfile.dagChatChannels

                await self.send(
                    ChatChannelsListMessage.make(channelsDag.channelsSorted)
                )

    async def shutdown(self):
        await super().shutdown()
        await self.send(UserChannelsListMessage.make([]))
        await asyncio.sleep(0.5)


class PSEncryptedChatChannelService(RSAEncryptedJSONPubsubService):
    def __init__(self, ipfsCtx, client,
                 channel: str, jwsToken, psKey, **kw):
        self.channel = channel
        self.psKey = psKey
        self.jwsToken = jwsToken
        self._chatPeers = []
        self.mChatService = ipfsCtx.pubsub.byTopic(TOPIC_CHAT)

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

        if cMsg.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_MESSAGE:
            if cMsg.command == ChatRoomMessage.COMMAND_HEARTBEAT:
                await self.processHeartbeat(sender, cMsg)

        await self.gHubPublish(self.psKey, (sender, cMsg))

    async def peersToSend(self):
        async for peer, sesskey in self.mChatService.peersByChannel(
                self.channel):
            piCtx = self.ipfsCtx.peers.getByPeerId(peer)
            yield (peer, piCtx, sesskey)

    async def processHeartbeat(self, sender, message):
        if sender not in self._chatPeers:
            self._chatPeers.append(sender)

    async def handleStatusMessage(self, sender, peerCtx, msg):
        sMsg = ChatStatusMessage(msg)
        if not sMsg.valid():
            self.debug('Invalid chat message')
            return

        sMsg.peerCtx = peerCtx
        await self.gHubPublish(self.psKey, sMsg)
