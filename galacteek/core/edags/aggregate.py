import os.path

from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs import ipfsOp
from galacteek.core.asynccache import cachedcoromethod
from cachetools import TTLCache


def _merge_dictionaries(dict1, dict2):
    """
    Recursive merge dictionaries.

    :param dict1: Base dictionary to merge.
    :param dict2: Dictionary to merge on top of base dictionary.
    :return: Merged dictionary
    """
    for key, val in dict1.items():
        if isinstance(val, dict):
            dict2_node = dict2.setdefault(key, {})
            _merge_dictionaries(val, dict2_node)
        else:
            if key not in dict2:
                dict2[key] = val

    return dict2


class AggregateDAG(EvolvingDAG):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.available.connectTo(self.onAvailable)

    def initDag(self):
        return {
            'nodes': {}
        }

    @property
    def nodes(self):
        return self.root['nodes']

    async def onAvailable(self, obj):
        pass

    @ipfsOp
    async def link(self, ipfsop, peerId, dagCid):
        if await ipfsop.pin(dagCid, recursive=True):
            async with self as dag:
                if peerId in dag.root['nodes']:
                    del dag.root['nodes'][peerId]

                dag.root['nodes'][peerId] = self.mkLink(dagCid)

    async def peerNode(self, peerId):
        if peerId in self.nodes:
            return await self.get(
                os.path.join('nodes', peerId)
            )

    @cachedcoromethod(TTLCache(16, 60))
    async def merged(self):
        m = {}
        for peer in self.nodes:
            node = await self.peerNode(peer)
            if isinstance(node, dict):
                m = _merge_dictionaries(m, node)
        return m


class MergeDAG(EvolvingDAG):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.available.connectTo(self.onAvailable)

    def initDag(self):
        return {
            'merge': {}
        }

    @property
    def nodes(self):
        return self.root['nodes']

    async def onAvailable(self, obj):
        pass

    @ipfsOp
    async def merge(self, ipfsop, peerId, dagCid):
        # Make sure we can pin it
        if await ipfsop.pin(dagCid, recursive=True):
            dag = await ipfsop.dagGet(dagCid)

            m = _merge_dictionaries(self.root['merge'], dag)
            self.root['merge'] = m

            await self.ipfsSave()
