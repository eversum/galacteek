import uuid

from galacteek import ensure
from galacteek import log
from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs.dag import DAGPortal
from galacteek.ipfs.dag import DAGError
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import cidValid
from galacteek.core.edags.aggregate import AggregateDAG
from galacteek.core import utcDatetimeIso


class SeedsPortal(DAGPortal):
    @property
    def description(self):
        return self.d['seed']['description']

    @property
    def name(self):
        return self.d['seed']['name']

    async def objects3(self):
        try:
            for name, descr in self.d['seed']['objects'].items():
                yield name, descr
        except Exception:
            pass

    async def icon(self):
        return await self.cat('seed/icon')

    async def objects(self):
        try:
            for idx, obj in enumerate(self.d['seed']['objects']):
                yield idx, obj
        except Exception:
            pass

    async def objects2(self):
        try:
            objs = await self.get('seed/objects')
            for name, descr in objs.items():
                yield name, descr
        except Exception:
            pass


class SeedsEDag(EvolvingDAG):
    def initDag(self):
        return {
            'params': {
                'seeduid': str(uuid.uuid4()) + str(uuid.uuid4()),
            },
            'signature': None,
            'c': {
                'seeds': {},
                'leaves': {}
            }
        }

    @property
    def uid(self):
        return self.root['params']['seeduid']

    @ipfsOp
    async def _clear(self, ipfsop):
        async with self as d:
            d.root['c']['seeds'] = {}

    @ipfsOp
    async def seed(self, ipfsop, name: str,
                   objectsInfo: list,
                   section='all',
                   description='',
                   icon=None,
                   author=None,
                   creatorDid=None,
                   license=None
                   ):

        profile = ipfsop.ctx.currentProfile

        ipid = await profile.userInfo.ipIdentifier()
        if not ipid:
            raise Exception('No IPID found')

        signedName = await ipid.pssSign64(name.encode())

        seedCid = await ipfsop.dagPut({
            'formatv': 0,
            'seed': {
                'name': name,
                'dateCreated': utcDatetimeIso(),
                'dateModified': utcDatetimeIso(),
                'icon': self.ipld(icon) if icon else None,
                'license': self.ipld(license) if license else None,
                'author': author,
                'creatorDid': creatorDid,
                'description': description,
                'pinRequest': {
                    'minproviders': 10
                },
                'objects': objectsInfo
            },
            'parent': None,
            'namesignature': {
                'pss': signedName.decode()
            }
        }, pin=True)

        if seedCid:
            try:
                cidSign = await ipid.pssSign64(seedCid.encode())

                async with self as dagw:
                    s = dagw.root['c']['seeds'].setdefault(section, {})
                    cur = s.setdefault(name, [])
                    cur.append({
                        '_metadata': {
                            'datecreated': utcDatetimeIso(),
                            'icon': self.ipld(icon) if icon else None,
                            'signature': cidSign.decode()
                        },
                        'seedlink': dagw.ipld(seedCid)
                    })

                return seedCid
            except Exception as err:
                log.debug(f'Error creating seed: {err}')
                raise err


class MegaSeedsEDag(AggregateDAG):
    async def _searchSubDag(self, pdag, root, regexp, path=None):
        for sname, section in root.items():
            lkeys = [key for key in section.keys() if not key.startswith('_')]

            for key in lkeys:
                ma = regexp.search(key)

                if not ma:
                    continue

                seeds = section[key]

                for idx, entry in enumerate(seeds):
                    meta = entry['_metadata']

                    link = entry['seedlink'].get('/')
                    if cidValid(link):
                        yield sname, key, meta['datecreated'], link

    async def search(self, regexp):
        for peer in self.nodes:
            try:
                async with self.portalToPath(
                        f'nodes/{peer}/link', dagClass=SeedsPortal) as pdag:
                    async for found in self._searchSubDag(
                            pdag,
                            pdag.root['c']['seeds'],
                            regexp):
                        yield found
            except DAGError:
                log.debug(f'Searching on node {peer} failed')
                continue
            except Exception:
                raise

    async def getSeed(self, seedCid):
        try:
            portal = SeedsPortal(dagCid=seedCid)
            await portal.load()
            return portal
        except Exception:
            pass

    async def expandSeed(self, seedCid):
        try:
            portal = DAGPortal(dagCid=seedCid)
            async with portal as seed:
                return await seed.expand()
        except Exception:
            return

    @ipfsOp
    async def _clear(self, ipfsop):
        async with self as d:
            d.root['nodes'] = {}

    @ipfsOp
    async def analyze(self, ipfsop, peerId, dagCid):
        # Pin seeds descriptors

        try:
            log.debug(f'Analyzing DAG: {dagCid} for {peerId}')
            async with SeedsPortal(dagCid=dagCid) as pdag:
                for sname, section in pdag.root['c']['seeds'].items():
                    lkeys = [key for key in section.keys() if
                             not key.startswith('_')]
                    for key in lkeys:
                        seeds = section[key]

                        for idx, entry in enumerate(seeds):
                            path = f'c/seeds/{sname}/{key}/{idx}/seedlink'
                            resolved = await pdag.resolve(path)
                            if resolved:
                                ensure(ipfsop.pin(resolved, timeout=30))

                    await ipfsop.sleep()
        except DAGError:
            return False
        else:
            return True
