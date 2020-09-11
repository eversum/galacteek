import hashlib

from galacteek import ensure
from galacteek import log
from galacteek import AsyncSignal
from galacteek.ipfs.dag import EvolvingDAG
from galacteek.ipfs.dag import DAGPortal
from galacteek.ipfs.dag import DAGError
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import cidValid
from galacteek.core.edags.aggregate import AggregateDAG
from galacteek.core import utcDatetimeIso
from galacteek.core import parseDate
from galacteek.core import jsonSchemaValidate
from galacteek.core import doubleUid4


def seedUdlHash(peerId, dagUid):
    m = hashlib.blake2b()
    m.update(f'{peerId}:{dagUid}'.encode())
    return m.hexdigest()


class SeedPortal(DAGPortal):
    @property
    def description(self):
        return self.d['seed']['description']

    @property
    def name(self):
        return self.d['seed']['name']

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


class SeedsCommon:
    @property
    def iterationUid(self):
        return self.root['params']['seediteruid']

    @property
    def iterationSig(self):
        return self.root['signatures']['iteration']


class SeedsPortal(DAGPortal, SeedsCommon):
    pass


class SeedsEDag(EvolvingDAG, SeedsCommon):
    schema = {
        "type": "object",
        "properties": {
            "c": {
                "type": "object",
                "properties": {
                    "seeds": {
                    }
                }
            },
            "params": {
                "type": "object",
                "properties": {
                    "seeduid": {
                        "type": "string",
                        "pattern": r"[0-9a-f\-]{72}"
                    },
                    "seedudbh": {
                        "type": "string",
                        "pattern": r"[0-9a-f]{96}"
                    }
                }
            },
            "required": [
                "c",
                "params"
            ]
        },
        "required": ["c", "params"]
    }

    def __init__(self, *args, **kw):
        super(SeedsEDag, self).__init__(*args, **kw)

        self.sSeedAdded = AsyncSignal(str)

    async def initDag(self, ipfsop):
        d = {
            'params': {
                'seeduid': doubleUid4(),
                'seediteruid': doubleUid4(),
                'seedudbh': None,
                'revnum': 0
            },
            'signatures': {
                'iteration': None
            },
            'c': {
                'seeds': {},
                'leaves': {},
                'reports': {}
            }
        }

        d['params']['seedudbh'] = seedUdlHash(
            ipfsop.ctx.node.id,
            d['params']['seeduid']
        )

        return d

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
                   comment='',
                   revision=0,
                   icon=None,
                   authorName=None,
                   authorEmail=None,
                   authorDid=None,
                   creatorDid=None,
                   creatorIpHandle=None,
                   licenseCid=None,
                   licenseName=None,
                   manifestCid=None,
                   cumulativeSize=0,
                   pinReqMin=10,
                   pinReqTarget=20,
                   tags=[],
                   keywords=[],
                   refid=None
                   ):

        profile = ipfsop.ctx.currentProfile

        ipid = await profile.userInfo.ipIdentifier()
        if not ipid:
            raise Exception('No IPID found')

        uid = doubleUid4()
        signedUid = await ipfsop.rsaAgent.pssSign64(uid.encode())

        preSeed = {
            'formatv': 0,
            'seed': {
                'name': name,
                'uid': uid,
                'revision': revision,
                'tags': tags,
                'dateCreated': utcDatetimeIso(),
                'dateModified': utcDatetimeIso(),
                'icon': self.ipld(icon) if icon else None,
                'license': {
                    'name': licenseName,
                    'link': self.ipld(licenseCid) if licenseCid else None
                },
                'author': {
                    'name': authorName,
                    'email': authorEmail,
                    'did': authorDid
                },
                'wallets': {},
                'creatorDid': creatorDid,
                'creatorIpHandle': creatorIpHandle,
                'description': description,
                'comment': comment,
                'manifests': [],
                'pinRequest': {
                    'minproviders': pinReqMin,
                    'targetproviders': pinReqTarget,
                    'p2pPinServiceUrl': None
                },
                'objects': objectsInfo,
                'cumulativeSize': cumulativeSize
            },
            'parent': None,
            'signatures': {
                'pss_uid': signedUid,
            }
        }

        if manifestCid:
            preSeed['seed']['manifests'].append(self.ipld(manifestCid))

        seedCid = await ipfsop.dagPut(preSeed, pin=True)

        if seedCid:
            try:
                cidSign = await ipfsop.rsaAgent.pssSign(seedCid.encode())
                if not cidSign:
                    raise Exception('Could not sign CID')

                cidSignEntry = await ipfsop.addBytes(cidSign)

                if not cidSignEntry:
                    raise Exception('Could not import CID signature')

                async with self as dagw:
                    s = dagw.root['c']['seeds'].setdefault(section, {})
                    cur = s.setdefault(name, [])

                    # We store some metadata to make it easier to search
                    # without loading the full seed DAG
                    cur.append({
                        '_metadata': {
                            'datecreated': utcDatetimeIso(),
                            'dateexpires': None,
                            'icon': self.ipld(icon) if icon else None,
                            'tags': tags,
                            'keywords': keywords,
                            'refid': refid,
                            'pss_cid_link': dagw.ipld(cidSignEntry)
                        },
                        'seedlink': dagw.ipld(seedCid)
                    })

                    # Regenerate an iteration UID
                    dagw.root['params']['revnum'] += 1
                    dagw.root['params']['seediteruid'] = doubleUid4()

                    # Sign the iteration

                    signedIter = await ipfsop.rsaAgent.pssSign64(
                        dagw.root['params']['seediteruid'].encode())

                    dagw.root['signatures']['iteration'] = signedIter

                await self.sSeedAdded.emit(seedCid)

                return seedCid
            except Exception as err:
                log.debug(f'Error creating seed: {err}')
                raise err


class MegaSeedsEDag(AggregateDAG):
    def __init__(self, *args, **kw):
        super(MegaSeedsEDag, self).__init__(*args, **kw)

        self.megaMergeHistory = {}

    def udbHash(self, peerId, dagUid):
        return seedUdlHash(peerId, dagUid)

    async def _searchSubDag(self, pdag, root, regexp, path=None,
                            dateFrom=None,
                            dateTo=None):

        for sname, section in root.items():
            lkeys = [key for key in section.keys() if not key.startswith('_')]

            for key in lkeys:
                ma = regexp.search(key)

                if not ma:
                    continue

                seeds = section[key]

                for idx, entry in enumerate(seeds):
                    meta = entry['_metadata']
                    datecreated = meta['datecreated']

                    link = entry['seedlink'].get('/')

                    if not cidValid(link):
                        continue

                    date = parseDate(datecreated)

                    if date and dateFrom and dateTo:
                        if date >= dateFrom and date <= dateTo:
                            yield sname, key, datecreated, link
                    else:
                        yield sname, key, datecreated, link

    async def search(self, regexp, dateFrom=None, dateTo=None):
        for peer in self.nodes:
            try:
                async with self.portalToPath(
                        f'nodes/{peer}/link',
                        dagClass=SeedsPortal) as pdag:
                    async for found in self._searchSubDag(
                            pdag,
                            pdag.root['c']['seeds'],
                            regexp,
                            dateFrom=dateFrom,
                            dateTo=dateTo):
                        yield found
            except DAGError:
                log.debug(f'Searching on node {peer} failed: dag error')
                continue
            except Exception as e:
                log.debug(f'Searching on node {peer} failed: {e}')
                continue

    async def getSeed(self, seedCid):
        try:
            portal = SeedPortal(dagCid=seedCid)
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
    async def analyze(self, ipfsop, peerId, dagCid, pubKeyPem):
        try:
            log.debug(f'Analyzing DAG: {dagCid} for {peerId}')

            async with SeedsPortal(dagCid=dagCid) as pdag:
                if not jsonSchemaValidate(SeedsEDag.schema, pdag.root):
                    log.debug(f'Analyzing DAG: {dagCid}: Schema INVALID')
                    return False
                else:
                    log.debug(f'Analyzing DAG: {dagCid}: Schema VALID !')

                await ipfsop.sleep()

                if not pdag.iterationSig:
                    # Not signed yet
                    return False

                if not await ipfsop.ctx.rsaExec.pssVerif64(
                        pdag.iterationUid.encode(),
                        pdag.iterationSig.encode(),
                        pubKeyPem):
                    log.debug(f'Analyzing DAG: {dagCid}: SIG WRONG')
                    return False
                else:
                    log.debug(f'Analyzing DAG: {dagCid}: SIG OK !')

                # Pin seeds descriptors
                for sname, section in pdag.root['c']['seeds'].items():
                    lkeys = [key for key in section.keys() if
                             not key.startswith('_')]
                    for key in lkeys:
                        seeds = section[key]

                        for idx, entry in enumerate(seeds):
                            path = f'c/seeds/{sname}/{key}/{idx}/seedlink'
                            resolved = await pdag.resolve(path)
                            if resolved:
                                ensure(ipfsop.pin(
                                    resolved, recursive=False, timeout=20))

                        await ipfsop.sleep()

                    await ipfsop.sleep()
        except DAGError as dage:
            log.debug(f'Analyzing DAG: {dagCid}: DAG error {dage}')
            return False
        except Exception as err:
            log.debug(f'Analyzing DAG: {dagCid}: unknown error {err}')
            return False
        else:
            return True

    @ipfsOp
    async def megaMerge(self, ipfsop,
                        peerId: str,
                        mDagCid: str,
                        signerPubKeyCid: str,
                        local=False):
        ltime = ipfsop.client.loop.time()

        try:
            lastMerge = self.megaMergeHistory.get(peerId)
            if lastMerge:
                if (ltime - lastMerge) < 60 * 15:
                    raise Exception('Merge postponed')

            pubKeyPem = await ipfsop.rsaPubKeyCheckImport(signerPubKeyCid)

            if not pubKeyPem:
                raise Exception(
                    f'Cannot fetch pubkey with CID: {signerPubKeyCid}')

            async with self as mega:  # <==== Mega EDAG write ^_^
                async with DAGPortal(mDagCid) as rPort:
                    aggiterUid = rPort.root['data']['aggiter_uid']
                    aggiterSig = rPort.root['signatures']['aggiter']

                    if not await ipfsop.ctx.rsaExec.pssVerif64(
                            aggiterUid.encode(),
                            aggiterSig.encode(),
                            pubKeyPem):
                        self.debug(
                            f'Mega merge {mDagCid} '
                            f'Invalid aggiter signature')
                        raise Exception('Could not verify top signature')
                    else:
                        self.debug(
                            f'Mega merge {mDagCid} '
                            f'Valid aggiter signature')

                    for udh, node in rPort.root['nodes'].items():
                        if udh in mega.root['nodes']:
                            self.debug(
                                f'Mega merge {mDagCid} '
                                f'Already have udh {udh}')
                            continue

                        try:
                            seedsCid = await rPort.resolve(
                                f'nodes/{udh}/link')
                            pubKeyPem = await rPort.cat(
                                f'nodes/{udh}/signerpubkey')

                            if not seedsCid or not pubKeyPem:
                                raise Exception('Invalid seeds link')

                            async with SeedsPortal(dagCid=seedsCid) as pdag:
                                assert pdag.root['params']['seedudbh'] == udh

                                if await ipfsop.ctx.rsaExec.pssVerif64(
                                        pdag.iterationUid.encode(),
                                        pdag.iterationSig.encode(),
                                        pubKeyPem):
                                    node = await rPort.get(f'nodes/{udh}')

                                    if node:
                                        # Branch
                                        mega.root['nodes'][udh] = node

                                        self.debug(
                                            f'Mega merge {mDagCid} : '
                                            f'Merged udh {udh}')
                                    else:
                                        self.debug(
                                            f'Mega merge {mDagCid} : '
                                            f'Could not merge udh {udh}')
                                else:
                                    self.debug(
                                        f'Mega merge {mDagCid} : '
                                        f'Wrong sig for {udh}')
                        except DAGError as err:
                            log.debug(f'Mega merge {seedsCid}: DAGErr {err}')
                            await ipfsop.sleep(0.1)
                            continue
                        except Exception as err:
                            log.debug(f'Mega merge {seedsCid}: ERR {err}')
                            await ipfsop.sleep(0.1)
                            continue
                        else:
                            log.debug(f'Mega merge {seedsCid}: OK')
                            await ipfsop.sleep(0.1)
                            continue
        except Exception as e:
            log.debug(f'Mega merge error: {e}')

        self.megaMergeHistory[peerId] = ltime
