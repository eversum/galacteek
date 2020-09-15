import os.path
import hashlib

from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.cidhelpers import stripIpfs
from galacteek.core.asynccache import cachedcoromethod
from galacteek.core import utcDatetimeIso
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
    def initDag(self):
        return {
            'nodes': {}
        }

    @property
    def nodes(self):
        return self.root['nodes']

    @ipfsOp
    async def analyze(self, ipfsop, peerId, dagCid):
        return True

    @ipfsOp
    async def link(self, ipfsop, peerId, dagUid, dagCid, local=False):
        self.debug(f'Branching for {peerId}')

        if not local:
            if not await ipfsop.pin(dagCid, recursive=True, timeout=120):
                self.debug(f'Branching for {peerId}: PIN {dagCid}: FAILED')
                return False
            else:
                self.debug(f'Branching for {peerId}: PIN {dagCid}: OK')

        valid = await self.analyze(peerId, dagCid)

        if not valid:
            self.debug(f'Invalid DAG: {dagCid}')
            return False
        else:
            self.debug(f'DAG is valid: {dagCid}')

        m = hashlib.sha3_256()
        m.update(f'{peerId}:{dagUid}'.encode())
        linkId = m.hexdigest()

        r = await self.resolve(f'nodes/{linkId}/link')
        self.debug(f'Branching for {peerId}: has {r}')

        if r and stripIpfs(r) == dagCid:
            self.debug(f'Branching for {peerId}: already at latest')
            return

        async with self as dag:
            dag.root['nodes'][linkId] = {
                'datebranched': utcDatetimeIso(),
                'link': self.ipld(dagCid)
            }

        return True

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
