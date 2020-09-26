from galacteek.core import utcDatetimeIso
from galacteek.ipfs import ipfsOp

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
    CHATMSG_TYPE_JOINED = 1
    CHATMSG_TYPE_LEFT = 2
    CHATMSG_TYPE_HEARTBEAT = 3

    schema = {
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},
            "ChatRoomMessage": {
                "type": "object",
                "properties": {
                    "chatmsgtype": {"type": "integer"},
                    "date": {"type": "string"},
                    "message": {"type": "string"},
                    "level": {"type": "integer"},
                    "links": {"type": "array"},
                    "attachments": {"type": "array"}
                },
                "required": [
                    "chatmsgtype",
                    "message",
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
    async def make(self, ipfsop, message='',
                   links=[], attachments=[], date=None,
                   type=CHATMSG_TYPE_MESSAGE,
                   level=0):
        msgDate = date if date else utcDatetimeIso()
        msg = ChatRoomMessage({
            'msgtype': ChatRoomMessage.TYPE,
            'version': 1,
            'ChatRoomMessage': {
                'uid': doubleUid4(),
                'chatmsgtype': type,
                'date': msgDate,
                'message': message,
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
    def message(self):
        return self.jsonAttr('ChatRoomMessage.message')

    @property
    def uid(self):
        return self.jsonAttr('ChatRoomMessage.uid')

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
            return len(self.message) < 1024 and self.chatMessageType in [
                ChatRoomMessage.CHATMSG_TYPE_MESSAGE,
                ChatRoomMessage.CHATMSG_TYPE_JOINED,
                ChatRoomMessage.CHATMSG_TYPE_LEFT,
                ChatRoomMessage.CHATMSG_TYPE_HEARTBEAT
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
                    "UserChannelsMessage": {
                        "channels": {
                            "type": "list"
                        }
                    }
                }
            }
        }
    }

    def make(chanlist):
        msg = UserChannelsListMessage({
            'msgtype': UserChannelsListMessage.TYPE,
            'UserChannelsMessage': {
                "channels": chanlist
            }
        })
        return msg

    @property
    def channels(self):
        return self.jsonAttr('UserChannelsMessage.channels')
