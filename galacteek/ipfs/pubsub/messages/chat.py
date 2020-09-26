from galacteek.core import utcDatetimeIso
from galacteek.ipfs import ipfsOp

from galacteek.ipfs.cidhelpers import ipfsCid32Re
from galacteek.ipfs.cidhelpers import ipfsLinkRe
from galacteek.ipfs.pubsub.messages import PubsubMessage
from galacteek.ipfs.pubsub.messages import LDMessage
from galacteek.core import doubleUid4


class ChatChannelsListMessage(PubsubMessage):
    TYPE = 'ChatChannelsListMessage'

    schema = {
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},
            "msg": {
                "type": "object",
                "properties": {
                    "channels": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^#[a-zA-Z-_]{1,64}"
                        }
                    }
                },
                "required": ["channels"]
            }
        },
        "required": ["msgtype", "msg"]
    }

    @staticmethod
    def make(channels: list):
        msg = ChatChannelsListMessage({
            'msgtype': ChatChannelsListMessage.TYPE,
            'version': 1,
            'msg': {
                'channels': channels
            }
        })
        return msg

    @property
    def channels(self):
        return self.jsonAttr('msg.channels')


class ChatStatusMessage(PubsubMessage):
    TYPE = 'ChatStatusMessage'

    STATUS_HEARTBEAT = 0
    STATUS_JOINED = 1
    STATUS_LEFT = 2

    schema = {
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},
            "msg": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "integer"
                    }
                }
            }
        }
    }

    @ipfsOp
    async def make(self, ipfsop, status):
        msg = ChatStatusMessage({
            '@context': await ipfsop.ldContextJson(
                'messages/ChatStatusMessage'),
            'msgtype': ChatStatusMessage.TYPE,
            'ChatStatusMessage': {
                'status': status,
                'date': utcDatetimeIso()
            }
        })
        return msg

    @property
    def status(self):
        return self.jsonAttr('msg.status')


class ChatRoomMessage(LDMessage):
    TYPE = 'ChatRoomMessage'

    CHATMSG_TYPE_MESSAGE = 0

    COMMAND_MSG = 'MSG'
    COMMAND_MSGMARKDOWN = 'MSGMARKDOWN'
    COMMAND_HEARTBEAT = 'HEARTBEAT'
    COMMAND_JOIN = 'JOIN'
    COMMAND_LEAVE = 'LEAVE'

    schema = {
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},
            "ChatRoomMessage": {
                "type": "object",
                "properties": {
                    "chatmsgtype": {"type": "integer"},
                    "date": {"type": "string"},
                    "command": {"type": "string"},
                    "jwsTokenCid": {
                        "type": "string",
                        "pattern": ipfsCid32Re.pattern
                    },
                    "params": {
                        "type": "array",
                        "maxItems": 8
                    },
                    "level": {"type": "integer"},
                    "links": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": ipfsLinkRe.pattern
                        },
                        "maxItems": 4,
                        "uniqueItems": True
                    },
                    "attachments": {"type": "array"}
                },
                "required": [
                    "jwsTokenCid",
                    "chatmsgtype",
                    "command",
                    "params",
                    "date",
                    "level"
                ]
            },
        },
        "required": [
            "msgtype",
            "ChatRoomMessage"
        ]
    }

    @ipfsOp
    async def make(self, ipfsop,
                   jwsCid,
                   links=[], attachments=[], date=None,
                   type=CHATMSG_TYPE_MESSAGE,
                   command='MSG',
                   params=[],
                   level=0):
        msgDate = date if date else utcDatetimeIso()
        msg = ChatRoomMessage({
            'msgtype': ChatRoomMessage.TYPE,
            'version': 1,
            'ChatRoomMessage': {
                'uid': doubleUid4(),
                'jwsTokenCid': jwsCid,
                'chatmsgtype': type,
                'date': msgDate,
                'command': command,
                'params': params,
                'links': links,
                'attachments': attachments,
                'level': level
            }
        })
        return msg

    @property
    def chatMessageType(self):
        return self.jsonAttr('ChatRoomMessage.chatmsgtype')

    @property
    def params(self):
        return self.jsonAttr('ChatRoomMessage.params')

    @property
    def message(self):
        if self.command in ['MSG', 'MSGMARKDOWN']:
            return self.jsonAttr('ChatRoomMessage.params.0')

    @property
    def body(self):
        return self.message

    @property
    def command(self):
        return self.jsonAttr('ChatRoomMessage.command')

    @property
    def uid(self):
        return self.jsonAttr('ChatRoomMessage.uid')

    @property
    def jwsTokenCid(self):
        return self.jsonAttr('ChatRoomMessage.jwsTokenCid')

    @property
    def date(self):
        return self.jsonAttr('ChatRoomMessage.date')

    @property
    def level(self):
        return self.jsonAttr('ChatRoomMessage.level')

    @property
    def links(self):
        return self.data['ChatRoomMessage']['links']

    def valid(self):
        schemaOk = self.validSchema(schema=ChatRoomMessage.schema)
        if schemaOk:
            return self.chatMessageType in [
                ChatRoomMessage.CHATMSG_TYPE_MESSAGE
            ]


class UserChannelsListMessage(PubsubMessage):
    TYPE = 'ChatUserChannelsMessage'

    schema = {
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},

            "msg": {
                "type": "object",
                "properties": {
                    "rev": {
                        "type": "integer"
                    },
                    "pubChannels": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sessionJwsCid": {
                                    "type": "string",
                                    "pattern": ipfsCid32Re.pattern
                                }
                            },
                            "required": ["sessionJwsCid"]
                        },
                        "maxItems": 32
                    }
                },
                "required": ["pubChannels", "rev"]
            }
        },
        "required": ["msgtype", "msg"]
    }

    def make(revision: int, pubchanlist: list):
        return UserChannelsListMessage({
            'msgtype': UserChannelsListMessage.TYPE,
            'version': 1,
            'msg': {
                'rev': revision,
                'pubChannels': pubchanlist,
                'privChannels': {}
            }
        })

    @property
    def pubChannels(self):
        return self.jsonAttr('msg.pubChannels')

    @property
    def rev(self):
        return self.jsonAttr('msg.rev')
