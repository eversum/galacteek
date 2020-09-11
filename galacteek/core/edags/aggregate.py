import os.path
import uuid

from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs import ipfsOp
from galacteek.ipfs import kilobytes
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
    async def initDag(self, ipfsop):
        return {
            'nodes': {},
            'data': {
                'aggiter_uid': None
            },
            'signatures': {
                'aggiter': None
            }
        }

    @property
    def nodes(self):
        return self.root['nodes']

    @ipfsOp
    async def analyze(self, ipfsop, peerId, dagCid):
        return True

    @ipfsOp
    async def megaMerge(self, ipfsop,
                        peerId: str,
                        mDagCid: str,
                        signerPubKeyCid: str,
                        local=False):
        raise Exception('Not implemented')

    @ipfsOp
    async def link(self, ipfsop,
                   peerId: str,
                   dagUid: str,
                   dagCid: str,
                   signerPubKeyCid: str,
                   local=False):

        self.debug(f'Branching for {peerId}')

        if not local:
            if not await ipfsop.pin(dagCid, recursive=False, timeout=120):
                self.debug(f'Branching for {peerId}: PIN {dagCid}: FAILED')
                return False
            else:
                self.debug(f'Branching for {peerId}: PIN {dagCid}: OK')

        pubKeyStatInfo = await ipfsop.objStatInfo(signerPubKeyCid)
        if not pubKeyStatInfo.valid or \
                pubKeyStatInfo.dataLargerThan(kilobytes(32)):
            return False

        pubKeyPem = await ipfsop.catObject(
            signerPubKeyCid, timeout=10)

        if not pubKeyPem:
            raise Exception(f'Cannot fetch pubkey with CID: {signerPubKeyCid}')

        # Keep it
        await ipfsop.pin(signerPubKeyCid, recursive=False, timeout=5)

        valid = await ipfsop.waitFor(
            self.analyze(peerId, dagCid, pubKeyPem),
            60
        )

        if not valid:
            self.debug(f'Invalid DAG: {dagCid}')
            return False
        else:
            self.debug(f'DAG is valid: {dagCid}')

        linkId = self.udbHash(peerId, dagUid)

        r = await self.resolve(f'nodes/{linkId}/link')
        self.debug(f'Branching for {peerId}: has {r}')

        if r and stripIpfs(r) == dagCid:
            self.debug(f'Branching for {peerId}: already at latest')
            return False

        # Link it
        async with self as dag:
            dag.root['nodes'][linkId] = {
                'datebranched': utcDatetimeIso(),
                'signerpubkey': self.ipld(signerPubKeyCid),
                'link': self.ipld(dagCid)
            }

            dag.root['data']['aggiter_uid'] = str(uuid.uuid4())
            sig = await ipfsop.ctx.rsaAgent.pssSign64(
                dag.root['data']['aggiter_uid'].encode())

            if sig:
                dag.root['signatures']['aggiter'] = sig

        # Link OK
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

    async def initDag(self, ipfsop):
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
