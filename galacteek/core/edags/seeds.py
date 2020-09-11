
from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.core.edags.aggregate import AggregateDAG

import re


class SeedsEDag(EvolvingDAG):
    def initDag(self):
        return {
            'seeds': {}
        }

    async def seedO(self, name: str, cid: str):
        comps = name.split()

        async with self as dagw:
            cur = dagw.root['seeds']

            for comp in comps:
                cur = cur.setdefault(comp, {})

            cur['/'] = cid

    @ipfsOp
    async def seed(self, ipfsop, name: str, objectsPaths: list):
        comps = name.split()

        dEntry = await ipfsop.dagPut({
            'author': 'blah',
            'objects': objectsPaths
        })

        async with self as dagw:
            cur = dagw.root['seeds']

            for comp in comps:
                cur = cur.setdefault(comp, {})

            if not '_sl' in cur:
                cur['_sl'] = []

            cur['_sl'].append({
                '/': dEntry
            })

            if 0:
                cur['__sdescr'] = {
                    'date': 'now',
                    '/': cid
                }


class MegaSeedsEDag(AggregateDAG):
    async def _searchSubDag(self, pdag, root, comps, path=None):
        clen = len(comps)
        cur = root
        path = path if path else []

        #for idx, comp in enumerate(comps):
        for idx in range(0, clen):
            try:
                comp = comps.pop(0)
            except:
                break

            path.append(comp)

            print(idx, comp, comps)
            lkeys = [key for key in cur.keys() if not key.startswith('_')]

            for key in lkeys:
                ma = re.search(comp, key)

                if not ma:
                    continue

                print('match', comp, key)

                if len(comps) == 0:
                    #link = await self.resolve(key)
                    #link = cur[key].get('/')
                    #descr = cur[key].get('__sdescr')
                    descr = cur[key].get('_sl', [])

                    for entry in descr:
                        link = entry.get('/')
                        print('found link', key, descr, link)
                        if link:
                            yield path, link
                else:
                    async for found in self._searchSubDag(pdag, cur[key],
                            comps, path=path):
                        yield found

    async def _searchSubDag_NO(self, pdag, root, comps):
        clen = len(comps)
        cur = root

        for idx in range(0, clen):
            try:
                comp = comps.pop(0)
            except:
                print('WTF', idx)
                break

            found = False
            print(idx, comp, comps)
            lkeys = cur.keys()

            for key in lkeys:
                ma = re.search(comp, key)

                if not ma:
                    continue

                print('match', comp, key)
                found = True
                cur = cur[key]

            if not found:
                break

            if len(comps) == 0:
                link = cur.get('/')
                print('empty at', cur, link)
                if link:
                    yield link

    async def search(self, name):
        comps = name.split()
        for peer in self.nodes:
            async with self.portalToPath('nodes/' + peer) as pdag:
                async for found in self._searchSubDag(pdag, pdag.root['seeds'], comps):
                    yield found
