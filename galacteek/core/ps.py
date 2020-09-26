import aiopubsub
import functools

gHub = aiopubsub.Hub()

publisher = aiopubsub.Publisher(gHub, prefix=aiopubsub.Key('g'))


def makeKeyChatChannel(channel):
    return aiopubsub.Key('g', 'chat', 'channels', channel)


@functools.lru_cache(maxsize=1)
def makeKeyChatUsersList(channel):
    return aiopubsub.Key('g', 'pubsub', 'chatuserslist', channel)


@functools.lru_cache(maxsize=1)
def makeKeyPubChatTokens(channel):
    return aiopubsub.Key('g', 'pubsub', 'tokens', 'pubchat', channel)


def psSubscriber(sid):
    return aiopubsub.Subscriber(gHub, sid)


keyAll = aiopubsub.Key('*')

keyPsJson = aiopubsub.Key('g', 'pubsub', 'json')
keyPsEncJson = aiopubsub.Key('g', 'pubsub', 'enc', 'json')

keyChatAll = aiopubsub.Key('g', 'pubsub', 'chat', '*')
keyChatChannels = aiopubsub.Key('g', 'pubsub', 'chat', 'channels')

keyChatChanList = aiopubsub.Key('g', 'pubsub', 'userchanlist')
keyChatChanListRx = aiopubsub.Key('g', 'pubsub', 'userchanlist', 'rx')

keyChatChanUserList = aiopubsub.Key('g', 'pubsub', 'chatuserlist', 'rx')
keyChatTokens = aiopubsub.Key('g', 'pubsub', 'chattokens')

keyTokensDagExchange = aiopubsub.Key('g', 'tokens', 'dagexchange')
keySnakeDagExchange = aiopubsub.Key('g', 'dagexchange', 'snake')
keyTokensIdent = aiopubsub.Key('g', 'tokens', 'ident')

mSubscriber = psSubscriber('main')
