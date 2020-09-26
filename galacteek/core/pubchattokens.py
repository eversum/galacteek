import asyncio
import attr

from galacteek import AsyncSignal
from galacteek.core import SingletonDecorator
from galacteek.database import *


@SingletonDecorator
class PubChatTokensManager:
    def __init__(self, inactiveMax=60):
        self.__tokens = {}
        self.__byChannel = {}
        self.inactiveMax = inactiveMax
        self.active = True

        self.sChanChanged = AsyncSignal(str)
        self.sTokenStatus = AsyncSignal(str, str, int)

    async def start(self):
        await pubChatTokensClear()

    async def reg(self, jwsCid, channel, secTopic, peerId):
        token = await pubChatTokenNew(jwsCid, channel, secTopic, peerId)

        await self.sChanChanged.emit(channel)
        await self.sTokenStatus.emit(jwsCid, channel, 0)

        return token

    async def tokenGet(self, jwsCid):
        return await pubChatTokenGet(jwsCid)

    async def tokenUpdate(self, jwsCid):
        token = await self.tokenGet(jwsCid)
        if token:
            token.ltLast = loopTime()
            await token.save()

    async def tokenDestroy(self, jwsCid):
        await pubChatTokenDelete(jwsCid)

    async def tokensByChannel(self, channel):
        for token in await pubChatTokensByChannel(channel):
            yield token

    async def cleanup(self):
        now = loopTime()
        inactive = await pubChatTokensInactive(now - self.inactiveMax)

        for token in inactive:
            await self.sTokenStatus.emit(token.cid, token.channel, 1)
            await token.delete()

    async def cleanupTask(self):
        while self.active:
            await self.cleanup()
            await asyncio.sleep(30)


@attr.s(auto_attribs=True)
class PubChatToken:
    cid: str
    channel: str
    dtlast: float
    secTopic: str
    peerId: str


@SingletonDecorator
class InMemoryChatTokensManager:
    def __init__(self, inactiveMax=60):
        self.__tokens = {}
        self.__byChannel = {}
        self.lock = aiorwlock.RWLock()
        self.inactiveMax = inactiveMax
        self.active = True

        self.sChanChanged = AsyncSignal(str)
        self.sTokenStatus = AsyncSignal(str, str, int)

    async def reg(self, jwsCid, channel, secTopic, peerId):
        token = PubChatToken(
            cid=jwsCid,
            channel=channel, secTopic=secTopic,
            peerId=peerId,
            dtlast=loopTime()
        )

        self.__tokens[jwsCid] = token
        ct = self.__byChannel.setdefault(channel, weakreflist.WeakList())
        ct.append(token)

        await self.sChanChanged.emit(channel)
        await self.sTokenStatus.emit(jwsCid, channel, 0)

        return token

    def tokenGet(self, jwsCid):
        return self.__tokens.get(jwsCid)

    def tokenUpdate(self, jwsCid):
        token = self.tokenGet(jwsCid)
        if token:
            token.dtlast = loopTime()

    def tokenDestroy(self, jwsCid):
        if jwsCid in self.__tokens:
            del self.__tokens[jwsCid]

    async def tokensByChannel(self, channel):
        async with self.lock.reader_lock:
            if channel in self.__byChannel:
                for token in self.__byChannel[channel]:
                    yield token

    async def cleanup(self):
        now = loopTime()
        async with self.lock.writer_lock:
            for jwscid in list(self.__tokens.keys()):
                try:
                    token = self.__tokens[jwscid]
                    chan = token.channel

                    if (now - token.dtlast) > self.inactiveMax:
                        self.tokenDestroy(jwscid)

                        await self.sChanChanged.emit(chan)
                        await self.sTokenStatus.emit(jwscid, chan, 1)
                except Exception:
                    continue
