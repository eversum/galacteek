TOPIC_MAIN = 'galacteek.main'
TOPIC_PEERS = 'galacteek.peers'
TOPIC_CHAT = 'galacteek.chat'

TOPIC_HASHMARKS = 'galacteek.hashmarks'
TOPIC_DAGEXCH = 'galacteek.dagexchange'

TOPIC_ENC_CHAT_RSAAES = 'galacteek.rsaenc.pubchat'
TOPIC_ENC_CHAT_CURVE = 'galacteek.c25.pubchat'
TOPIC_ENC_CHAT_DEFAULT = 'galacteek.pubchat'


class MsgAttributeRecordError(Exception):
    pass


def encChatChannelTopic(channel):
    return f'{TOPIC_ENC_CHAT_DEFAULT}.{channel}'


def chatChannelTopic(channel):
    return f'{TOPIC_CHAT}.{channel}'
