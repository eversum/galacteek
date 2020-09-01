from galacteek.core import utcDatetimeIso
from galacteek.ipfs.dag import EvolvingDAG


class PeersGraphDAG(EvolvingDAG):
    def initDag(self):
        return {
            'peers': {},
            'datecreated': utcDatetimeIso(),
            'datemodified': utcDatetimeIso()
        }

    async def byDid(self, did: str):
        async with self.read() as portal:
            for peerId, peerHandles in portal.d['peers'].items():
                for handle, hData in peerHandles.items():
                    if hData.get('did') == did:
                        return hData

    async def didUpdateObj(self, did: str, docCid):
        async with self as g:
            for peerId, peerHandles in g.root['peers'].items():
                for handle, hData in peerHandles.items():
                    if hData.get('did') == did:
                        hData['didobj'] = self.ipld(docCid)
