import asyncio
import attr
import orjson
import re
import hashlib
import secrets

from galacteek import log
from galacteek import AsyncSignal
from galacteek.core import SingletonDecorator
from galacteek.core import utcDatetimeIso
from galacteek.core import doubleUid4
from galacteek.core import parseDate
from galacteek.core.message import Message
from galacteek.did import didIdentRe
from galacteek.ipfs.pubsub import encChatChannelTopic
from galacteek.ipfs.cidhelpers import ipfsCid32Re
from galacteek.database import *


class ChatToken(Message):
    schema = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "pattern": r"^(pubchattoken|privchattoken)$"
            },
            "version": {"type": "integer"},
            "token": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "maxLength": 48
                    },
                    "expires": {
                        "type": "string",
                        "maxLength": 48
                    },
                    "did": {
                        "type": "string",
                        "pattern": didIdentRe.pattern
                    },
                    "channel": {
                        "type": "string",
                        "pattern": r"^#[a-zA-Z0-9-_]{1,64}$"
                    },
                    "cpass": {
                        "type": "string",
                        "pattern": r"^[\w]{1,128}$"
                    },
                    "psTopic": {
                        "type": "string",
                        "pattern": r"^galacteek.[\w\.]{64,512}$"
                    },
                    "enc": {
                        "type": "object",
                        "properties": {
                            "etype": {
                                "type": "string",
                                "pattern": r"^(rsa-aes256-cbc|curve25519)$"
                            },
                            "pubKeyCid": {
                                "type": "string",
                                "pattern": ipfsCid32Re.pattern
                            }
                        },
                        "required": [
                            "etype"
                        ]
                    }
                },
                "required": [
                    "date"
                    "channel"
                    "did"
                    "psTopic",
                    "enc"
                ]
            }
        },
        "required": ["type", "version", "t"]
    }

    async def make(ipfsop, channel, pubKeyCid, encType='rsa-aes256-cbc'):
        curProfile = ipfsop.ctx.currentProfile
        try:
            hasher = hashlib.sha3_384()
            hasher.update('{peer}_{uid}'.format(
                peer=ipfsop.ctx.node.id,
                uid=doubleUid4()).encode())
            topic = encChatChannelTopic(hasher.hexdigest())
        except Exception:
            return None

        if encType == 'rsa-aes256-cbc':
            enc = {
                'etype': encType,
                'pubKeyCid': await ipfsop.rsaAgent.pubKeyCid()
            }
        elif encType == 'curve25519':
            enc = {
                'etype': encType,
                'pubKeyCid': pubKeyCid
            }
        else:
            enc = {}

        return ChatToken({
            'version': 1,
            'type': 'pubchattoken',
            't': {
                'date': utcDatetimeIso(),
                'did': curProfile.userInfo.personDid,
                'channel': channel,
                'psTopic': topic,
                'pubKeyCid': await ipfsop.rsaAgent.pubKeyCid(),
                'cpass': secrets.token_hex(8),
                'enc': enc
            }
        })

    @property
    def version(self):
        return self.jsonAttr('version')

    @property
    def date(self):
        return parseDate(self.jsonAttr('t.date'))

    @property
    def expires(self):
        return parseDate(self.jsonAttr('t.expires'))

    @property
    def channel(self):
        return self.jsonAttr('t.channel')

    @property
    def did(self):
        return self.jsonAttr('t.did')

    @property
    def psTopic(self):
        return self.jsonAttr('t.psTopic')

    @property
    def cpass(self):
        return self.jsonAttr('t.cpass')

    @property
    def encType(self):
        return self.jsonAttr('t.enc.etype')

    @property
    def pubKeyCid(self):
        return self.jsonAttr('t.enc.pubKeyCid')


def verifyTokenPayloadOld(payload: bytes):
    try:
        # Decode the token payload
        decoded = orjson.loads(payload.decode())

        psTopic = decoded.get('psTopic')
        chan = decoded.get('channel')
        did = decoded.get('did')
        cpass = decoded.get('pass')

        assert isinstance(psTopic, str)
        assert isinstance(chan, str)
        assert isinstance(did, str)
        assert isinstance(cpass, str)

        assert didIdentRe.match(did) is not None
        assert re.match(r"^#[a-zA-Z0-9-_]{1,64}$", chan) is not None
        assert re.match(r"^[\w]{1,128}$", cpass) is not None
        assert re.match(
            r"^galacteek.rsaenc.[\w\.]{64,256}$", psTopic) is not None
    except Exception as err:
        log.debug(f'Invalid JWS: {err}')
    else:
        return decoded


def verifyTokenPayload(payload: bytes):
    try:
        # Decode the token payload
        decoded = orjson.loads(payload.decode())

        token = ChatToken(decoded)
        assert token.valid() is True

        assert token.date is not None
    except Exception as err:
        log.debug(f'Invalid JWS: {err}')
    else:
        return token


@SingletonDecorator
class PubChatTokensManager:
    def __init__(self, inactiveMax=40):
        self.__tokens = {}
        self.__byChannel = {}
        self.inactiveMax = inactiveMax
        self.active = True

        self.sChanChanged = AsyncSignal(str)
        self.sTokenStatus = AsyncSignal(str, str, int)

    async def start(self):
        await pubChatTokensClear()

    async def reg(self, jwsCid, channel, secTopic, peerId, pubKeyCid,
                  **kw):
        token = await pubChatTokenNew(
            jwsCid, channel, secTopic, peerId, pubKeyCid=pubKeyCid, **kw)

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
