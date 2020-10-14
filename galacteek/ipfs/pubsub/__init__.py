TOPIC_MAIN = 'galacteek.main'
TOPIC_PEERS = 'galacteek.peers'
TOPIC_CHAT = 'galacteek.chat'
TOPIC_ENC_CHAT = 'galacteek.rsaenc.pubchat'
TOPIC_HASHMARKS = 'galacteek.hashmarks'
TOPIC_DAGEXCH = 'galacteek.dagexchange'


class MsgAttributeRecordError(Exception):
    pass


def encChatChannelTopic(channel):
    return f'{TOPIC_ENC_CHAT}.{channel}'


def chatChannelTopic(channel):
    return f'{TOPIC_CHAT}.{channel}'
