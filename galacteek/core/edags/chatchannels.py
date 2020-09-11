from py3crdt.gset import GSet

from galacteek import log
from galacteek.core.ps import keyChatChannels
from galacteek.core.ps import psSubscriber
from galacteek.ipfs.dag import EvolvingDAG

subscriber = psSubscriber('chat_channels_messages')


class ChannelsDAG(EvolvingDAG):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.gsetLocal = GSet(id='localchannels')
        self.available.connectTo(self.onAvailable)
        subscriber.add_async_listener(keyChatChannels, self.onChatChannels)

    async def initDag(self, ipfsop):
        return {
            'channels': {
                'all': [
                    '#galacteek',
                    '#ipfs'
                ],
                'favourites': []
            }
        }

    @property
    def channels(self):
        return self.root['channels']['all']

    @property
    def channelsSorted(self):
        return sorted(self.root['channels']['all'])

    async def onAvailable(self, obj):
        pass

    def register(self, channel):
        if self.channels and channel not in self.channels:
            log.debug('Registering channel: {}'.format(channel))

            self.channels.append(channel)
            self.changed.emit()

    async def onChatChannels(self, key, msg):
        await self.merge(msg.channels)

    async def merge(self, channels):
        if self.channelsSorted == channels:
            return

        set = GSet(id='remote')
        [set.add(chan) for chan in channels]

        for chan in self.channels:
            if not self.gsetLocal.query(chan):
                self.gsetLocal.add(chan)

        async with self.wLock:
            self.gsetLocal.merge(set)
            self.root['channels']['all'] = self.gsetLocal.payload

        self.changed.emit()
