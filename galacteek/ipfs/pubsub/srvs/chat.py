import asyncio

from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek.ipfs.pubsub import TOPIC_ENC_CHAT

from galacteek.ipfs.pubsub.service import JSONPubsubService
from galacteek.ipfs.pubsub.service import EncryptedJSONPubsubService

from galacteek.ipfs.pubsub.messages.chat import ChatRoomMessage
from galacteek.ipfs.pubsub.messages.chat import ChatStatusMessage
from galacteek.ipfs.pubsub.messages.chat import ChatChannelsListMessage
from galacteek.ipfs.pubsub.messages.chat import UserChannelsListMessage
from galacteek.ipfs.wrappers import ipfsOp

from galacteek.core.ps import keyChatChannels
from galacteek.core.ps import keyChatChanList
from galacteek.core.ps import keyChatChanListRx
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
        mSubscriber.add_async_listener(
            keyChatChanList, self.onUserChannelList)

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

    @ipfsOp
    async def handleUserChannelsMessage(self, ipfsop, sender, msg):
        cMsg = UserChannelsListMessage(msg)
        await self.gHubPublish(keyChatChanListRx, (sender, cMsg))

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
            if sender in self._chatPeers:
                self._chatPeers.remove(sender)

        await self.gHubPublish(self.psKey, (sender, cMsg))

    def peerEncFilter(self, piCtx, msg):
        if piCtx.peerId == self.ipfsCtx.node.id:
            return False

        if msg.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_HEARTBEAT:
            return False

        if msg.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_JOINED:
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
        await self.gHubPublish(self.psKey, sMsg)
