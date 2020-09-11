import aiopubsub

gHub = aiopubsub.Hub()

publisher = aiopubsub.Publisher(gHub, prefix=aiopubsub.Key('g'))

keyAll = aiopubsub.Key('*')

keyPsJson = aiopubsub.Key('g', 'pubsub', 'json')
keyChatAll = aiopubsub.Key('g', 'pubsub', 'chat', '*')
keyChatChannels = aiopubsub.Key('g', 'pubsub', 'chat', 'channels')

keyTokensDagExchange = aiopubsub.Key('g', 'tokens', 'dagexchange')
keyTokensIdent = aiopubsub.Key('g', 'tokens', 'ident')


def makeKeyChatChannel(channel):
    return aiopubsub.Key('g', 'chat', 'channels', channel)


def psSubscriber(sid):
    return aiopubsub.Subscriber(gHub, sid)
