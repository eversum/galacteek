import os
import os.path
import asyncio
import time
import re
import uuid
import getpass

import aiofiles

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtCore import QFile
from PyQt5.QtCore import QIODevice
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QAction

from galacteek import log
from galacteek import logUser
from galacteek import ensure
from galacteek import ensureLater
from galacteek import AsyncSignal

from galacteek.ipfs.mutable import MutableIPFSJson, CipheredIPFSJson
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.encrypt import IpfsRSAAgent
from galacteek.ipfs.dag import EvolvingDAG

from galacteek.did import didIdentRe
from galacteek.did.ipid import IPIdentifier
from galacteek.did.ipid import IPService

from galacteek.core.iphandle import ipHandleGen
from galacteek.core.iphandle import SpaceHandle
from galacteek.core.asynclib import asyncReadFile
from galacteek.core.orbitdb import OrbitConfigMap
from galacteek.core.orbitdbcfg import defaultOrbitConfigMap
from galacteek.core.jsono import QJSONFile
from galacteek.core.models.mfs import createMFSModel
from galacteek.core.ipfsmarks import IPFSMarks

from galacteek.core.userdag import UserDAG
from galacteek.core.userdag import UserWebsite
from galacteek.core.edags.chatchannels import ChannelsDAG
from galacteek.core.edags.ngraph import PeersGraphDAG

from galacteek.core.edags.seeds import SeedsEDag
from galacteek.core.edags.seeds import MegaSeedsEDag

from galacteek.core import utcDatetimeIso

from galacteek.crypto.qrcode import IPFSQrEncoder

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs.cidhelpers import joinIpfs

from galacteek.dweb import render


class CipheredHashmarks(CipheredIPFSJson):
    pass


class OrbitalProfileConfig(MutableIPFSJson):
    def configMap(self):
        return OrbitConfigMap(self.root['config'])

    @property
    def valid(self):
        return 'config' in self.root

    def initObj(self):
        return {
            'config': {}
        }


class IPHandlesDAG(EvolvingDAG):
    def initDag(self):
        return {
            'iphandles': []
        }

    async def register(self, ipHandle):
        self.root['iphandles'].append(ipHandle)
        self.changed.emit()


class UserProfileEDAG(EvolvingDAG):
    IDENTFLAG_READONLY = 1 << 1

    def initDag(self):
        now = utcDatetimeIso()

        return {
            'identities': {},
            'followingGlobal': {},
            'currentIdentityUid': None,

            'datecreated': now,
            'datemodified': now
        }

    @property
    def curIdentity(self):
        if self.root['currentIdentityUid']:
            return self.root['identities'].get(
                self.root['currentIdentityUid'])

    @property
    def username(self):
        return self.identityAttr('username')

    @property
    def email(self):
        return self.identityAttr('email')

    @property
    def iphandle(self):
        return self.identityAttr('iphandle')

    @property
    def spaceHandle(self):
        return SpaceHandle(self.iphandle)

    @property
    def iphandleValid(self):
        return SpaceHandle(self.iphandle).valid

    @property
    def personDid(self):
        return self.identityAttr('personDid')

    @property
    def vplanet(self):
        return self.identityAttr('vplanet')

    @property
    def avatar(self):
        return self.identityAttr('avatar')

    def identityAttr(self, attr):
        if self.curIdentity:
            return self.curIdentity.get(attr)

    @ipfsOp
    async def identityResolve(self, ipfsop, path):
        if self.curIdentity:
            return await self.resolve(os.path.join(
                'identities',
                self.root['currentIdentityUid'],
                path)
            )

    @ipfsOp
    async def identityDagGet(self, ipfsop, path, identityUid=None):
        return await self.get(os.path.join(
            'identities',
            identityUid if identityUid else self.root['currentIdentityUid'],
            path)
        )

    @ipfsOp
    async def identityGetRaw(self, ipfsop, path, identityUid=None):
        return await self.cat(os.path.join(
            'identities',
            identityUid if identityUid else self.root['currentIdentityUid'],
            path)
        )

    @ipfsOp
    async def getAvatar(self, ipfsop):
        return await self.get('avatar')

    async def follow(self, did, iphandle):
        log.debug('Following {}'.format(did))

        async with self as uInfo:
            section = uInfo.root['followingGlobal'].setdefault('main', {})
            section[did] = {
                'iphandle': iphandle
            }

    async def followingAll(self, section='main'):
        section = self['followingGlobal'].setdefault(section, {})

        for did, info in section.items():
            yield did, info

    async def identitiesIter(self):
        async with self.read() as portal:
            for uid, identity in portal.root['identities'].items():
                yield uid, identity

    async def ipHandleExists(self, iphandle):
        async for uid, identity in self.identitiesIter():
            if identity['iphandle'] == iphandle:
                return True

        return False

    @ipfsOp
    async def createIdentity(self, ipfsop, peered=False,
                             personDid=None, setAsCurrent=True,
                             iphandle=None,
                             bio=None,
                             flags=None):
        # You never know ..

        uid = str(uuid.uuid4())
        while uid in self.root['identities'].keys():
            uid = str(uuid.uuid4())

        pFlags = flags if isinstance(flags, int) else 0

        qr = await self.encodeIpHandleQr(
            iphandle, personDid
        )

        bioEntry = await ipfsop.addString(
            bio if bio else '# Bio')

        identity = {
            'email': None,
            'flags': pFlags,

            'iphandle': iphandle,
            'iphandleqr': {
                'png': self.mkLink(qr)
            },

            'vplanet': 'Earth',

            # DIDS
            'personDid': personDid,
            'following': {},

            'avatar': self.mkLink(
                await ipfsop.importQtResource(
                    '/share/icons/ipfs-cube-64.png'
                )
            ),

            'bio': self.mkLink(bioEntry),

            'crypto': {},
            'datecreated': utcDatetimeIso(),
            'datemodified': utcDatetimeIso()
        }

        async with self as dag:
            dag.root['identities'][uid] = identity

            if setAsCurrent:
                dag.root['currentIdentityUid'] = uid

        log.debug('Created identity', uid)
        return uid, dag.root['identities'][uid]

    @ipfsOp
    async def createIdentityPeered(self, ipfsop, **kw):
        return await self.createIdentity(
            peered=True,
            **kw
        )

    @ipfsOp
    async def ipIdentifier(self, ipfsop):
        if self.personDid:
            return await ipfsop.ipidManager.load(
                self.personDid,
                timeout=5,
                localIdentifier=True
            )

    @ipfsOp
    async def encodeIpHandleQr(self, ipfsop,
                               iphandle,
                               did,
                               format='png',
                               filename=None):
        encoder = IPFSQrEncoder()

        try:
            entry = await ipfsop.addString(iphandle, pin=True, only_hash=True)
            if not entry:
                return

            await ipfsop.sleep()

            encoder.add(joinIpfs(entry['Hash']))
            encoder.add(joinIpns(ipfsop.ctx.node.id))

            if didIdentRe.match(did):
                encoder.add(did)

            return await encoder.encodeAndStore(format=format)
        except Exception:
            pass


class ProfileError(Exception):
    pass


class SharedHashmarksManager(QObject):
    hashmarksLoaded = pyqtSignal(str, IPFSMarks)

    def __init__(self, parent):
        super(SharedHashmarksManager, self).__init__(parent)
        self._profile = parent
        self._state = {}
        self._loaded = []

    @property
    def profile(self):
        return self._profile

    async def loadFromPath(self, path):
        marksCiphered = CipheredHashmarks(path, self.profile.rsaAgent)
        await marksCiphered.load()
        return marksCiphered

    async def scanningTask(self):
        while True:
            await self.scan()
            await asyncio.sleep(60)

    @ipfsOp
    async def scan(self, ipfsop):
        log.debug('Scanning hashmarks MFS library')

        listing = await ipfsop.filesList(self.profile.pathHMarksLibrary)

        for file in listing:
            await ipfsop.sleep()

            uid = file['Name']
            marksHash = file['Hash']

            if marksHash in self._loaded:
                continue

            fPath = os.path.join(self.profile.pathHMarksLibrary, uid)

            try:
                marksCiphered = await self.loadFromPath(fPath)

                marks = IPFSMarks(None, data=marksCiphered.root)
                self.hashmarksLoaded.emit(uid, marks)
                self._loaded.append(marksHash)
            except BaseException as err:
                log.debug('Could not load hashmarks from CID {0}: {1}'.format(
                    marksHash, str(err)))
            else:
                logUser.info('Loaded hashmarks from peer {0}'.format(uid))
                await asyncio.sleep(1)

    async def store(self, ipfsop, sender, marksJson):
        mfsPath = os.path.join(self.profile.pathHMarksLibrary, sender)

        exists = await ipfsop.filesLookup(self.profile.pathHMarksLibrary,
                                          sender)
        if not exists:
            marks = CipheredHashmarks(
                mfsPath, self.profile.rsaAgent, data=marksJson)
            await marks.ipfsSave()
            self._state[sender] = marks
        else:
            if sender not in self._state:
                marks = CipheredHashmarks(
                    mfsPath, self.profile.rsaAgent)
                await marks.load()
                self._state[sender] = marks
                marks._root = marksJson
                marks.changed.emit()
            else:
                marks = self._state[sender]
                marks._root = marksJson
                marks.changed.emit()

        await asyncio.sleep(1)


class DIDRsaKeyStore:
    def __init__(self, profile, _storeRoot):
        self.__root = _storeRoot
        self.__profile = profile

    def _privateKeyPathForDid(self, did):
        match = didIdentRe.match(did)
        if not match:
            return None

        return os.path.join(
            self.__root,
            'rsa_{0}_ipid_{1}_priv.key'.format(
                self.__profile, match.group('id')
            )
        )

    def _privateKeyForDid(self, did):
        from Cryptodome.PublicKey import RSA

        privKeyPath = self.__privateKeyPathForDid(did)
        if not privKeyPath:
            return

        if os.path.isfile(privKeyPath):
            try:
                with open(privKeyPath, 'rb') as fd:
                    privKey = RSA.import_key(fd.read())
            except Exception:
                return None
            else:
                return privKey


class UserProfile(QObject):
    """
    User profile object
    """

    qrImageEncoded = AsyncSignal(bool, str)
    webPageSaved = AsyncSignal(dict, str)

    identityChanged = AsyncSignal(str, str)

    def __init__(self, ctx, name, rootDir):
        super(UserProfile, self).__init__()

        self._ctx = ctx
        self._name = name
        self._rootDir = rootDir
        self._initialized = False

        self.keyRoot = 'galacteek.{}.root'.format(self.name)
        self.keyRootId = None
        self.keyMainDid = self.ipIdentifierKeyName(idx=0)

        self._didKeyStore = DIDRsaKeyStore(
            self._name,
            self.ctx.app.cryptoDataLocation
        )

        self._rsaPrivKeyPath = os.path.join(
            self.ctx.app.cryptoDataLocation,
            'rsa_{0}_priv.key'.format(
                self.name))
        self._rsaPubKeyPath = os.path.join(self.ctx.app.cryptoDataLocation,
                                           'rsa_{0}_pub.key'.format(self.name))
        self._rsaPubKey = None

        self._filesModel = None

        self._dagUser = None

        self.userInfo = None
        self.ipHandles = IPHandlesDAG(
            self.edagMetadataPath('iphandles'), offline=True)

        self.orbitalConfigMfs = None
        self.orbitalCfgMap = None

        self.rsaAgent = None
        self.sharedHManager = SharedHashmarksManager(self)

        self.qrImageEncoded.connectTo(self.onQrImageEncoded)
        self.webPageSaved.connectTo(self.onWebPageSaved)
        self.identityChanged.connectTo(self.onIdentitySwitch)

    def debug(self, msg):
        log.debug('Profile {0}: {1}'.format(self.name, msg))

    def userLogInfo(self, msg):
        logUser.info('profile ({0}): {1}'.format(self.name, msg))

    @property
    def initialized(self):
        return self._initialized

    @property
    def rsaExec(self):
        return self.ctx.rsaExec

    @property
    def rsaPrivKeyPath(self):
        return self._rsaPrivKeyPath

    @property
    def rsaPubKeyPath(self):
        return self._rsaPubKeyPath

    @property
    def rsaPubKey(self):
        return self._rsaPubKey

    @rsaPubKey.setter
    def rsaPubKey(self, key):
        self._rsaPubKey = key

    @property
    def dagUser(self):
        return self._dagUser  # the DAG for this user

    @property
    def dagChatChannels(self):
        return self._dagChatChannels

    @property
    def dagNetwork(self):
        return self._dagNetwork

    @property
    def root(self):
        return self._rootDir  # profile's root dir in the MFS

    @property
    def ctx(self):
        return self._ctx  # IPFS context

    @property
    def name(self):
        return self._name

    @property
    def filesModel(self):
        return self._filesModel

    @filesModel.setter
    def filesModel(self, model):
        self._filesModel = model

    @property
    def tree(self):
        # Profile's filesystem tree list
        return [
            self.pathFiles,
            self.pathHome,
            self.pathMedia,
            self.pathData,
            self.pathHMarksLibrary,
            self.pathPlaylists,
            self.pathImages,
            self.pathPictures,
            self.pathVideos,
            self.pathDocuments,
            self.pathQrCodes,
            self.pathQrCodesEncrypted,
            self.pathMusic,
            self.pathCode,
            self.pathWebPages,
            self.pathDWebApps,
            self.pathTmp,
            self.pathEncryptedFiles,
            self.pathEDagsPyramids,
            self.pathEDagsSeeds
        ]

    @property
    def pathFiles(self):
        return os.path.join(self.root, 'files')

    @property
    def pathHome(self):
        return os.path.join(self.pathFiles, 'home')

    @property
    def pathDocuments(self):
        return os.path.join(self.pathFiles, 'documents')

    @property
    def pathTmp(self):
        return os.path.join(self.pathFiles, 'tmp')

    @property
    def pathEncryptedFiles(self):
        return os.path.join(self.pathFiles, 'sencrypted')

    @property
    def pathQrCodes(self):
        return os.path.join(self.pathMedia, 'qrcodes')

    @property
    def pathQrCodesEncrypted(self):
        return os.path.join(self.pathQrCodes, 'encrypted')

    @property
    def pathMedia(self):
        return os.path.join(self.pathFiles, 'multimedia')

    @property
    def pathImages(self):
        return os.path.join(self.pathMedia, 'images')

    @property
    def pathPictures(self):
        return os.path.join(self.pathMedia, 'pictures')

    @property
    def pathWebPages(self):
        return os.path.join(self.pathFiles, 'webpages')

    @property
    def pathDWebApps(self):
        return os.path.join(self.pathFiles, 'dwebapps')

    @property
    def pathVideos(self):
        return os.path.join(self.pathMedia, 'videos')

    @property
    def pathMusic(self):
        return os.path.join(self.pathMedia, 'music')

    @property
    def pathCode(self):
        return os.path.join(self.pathFiles, 'code')

    @property
    def pathWebsites(self):
        return os.path.join(self.pathFiles, 'websites')

    @property
    def pathEtc(self):
        return os.path.join(self.root, 'etc')

    @property
    def pathData(self):
        return os.path.join(self.root, 'data')

    @property
    def pathEDags(self):
        return os.path.join(self.pathData, 'edags')

    @property
    def pathEDagsSeeds(self):
        return os.path.join(self.pathEDags, 'seeds')

    @property
    def pathEDagsPyramids(self):
        return os.path.join(self.pathEDags, 'pyramids')

    @property
    def pathHMarksLibrary(self):
        return os.path.join(self.pathData, 'hmarks_library')

    @property
    def pathOrbital(self):
        return os.path.join(self.pathData, 'orbital')

    @property
    def pathOrbitalConfig(self):
        return os.path.join(self.pathOrbital, 'config')

    @property
    def pathPlaylists(self):
        return os.path.join(self.pathData, 'playlists')

    @property
    def pathUserInfo(self):
        return os.path.join(self.pathData, 'userinfo.json.enc')

    @property
    def pathProfileEDag(self):
        return self.edagMetadataPath('profile')

    @property
    def pathUserDagMeta(self):
        return os.path.join(self.pathData, 'dag.main')

    @property
    def pathChatChannelsDagMeta(self):
        return os.path.join(self.pathEDags, 'chatchannels.edag')

    @property
    def pathEDagNetwork(self):
        return os.path.join(self.pathEDags, 'network.edag')

    @property
    def pathEdagSeedsMain(self):
        return os.path.join(self.pathEDagsSeeds, 'seeds_main.edag')

    @property
    def pathEdagSeedsAll(self):
        return os.path.join(self.pathEDagsSeeds, 'seeds_agg.edag')

    @property
    def pathMDagShares(self):
        return os.path.join(self.pathEDags, 'mdag.shares.edag')

    def setFilesModel(self, model):
        self.filesModel = model

    @ipfsOp
    async def init(self, ipfsop):
        """
        Initialize the profile's filesystem
        """

        self.userLogInfo('Initializing filesystem')

        await ipfsop.filesMkdir(self.root)

        for directory in self.tree:
            await ipfsop.filesMkdir(directory)

        self.filesModel = createMFSModel()
        self.filesModel.setupItemsFromProfile(self)

        key = await ipfsop.keyFind(self.keyRoot)
        if key is not None:
            self.keyRootId = key.get('Id', None)
        else:
            self.userLogInfo('Generating main IPNS key')
            result = await ipfsop.keyGen(self.keyRoot)
            self.keyRootId = result.get('Id', None)

        self.debug('IPNS key({0}): {1}'.format(self.keyRoot, self.keyRootId))

        self.userLogInfo('Initializing crypto')

        if not await self.cryptoInit():
            self.userLogInfo('Error while initializing crypto')
            raise ProfileError('Crypto init failed')

        if not await ipfsop.hasDagCommand():
            self.userLogInfo('No DAG API! ..')
            return

        self.userLogInfo('Loading DAG ..')
        self._dagUser = UserDAG(self.pathUserDagMeta, loop=self.ctx.loop)

        self._dagChatChannels = ChannelsDAG(
            self.pathChatChannelsDagMeta, loop=self.ctx.loop)

        self._dagNetwork = PeersGraphDAG(
            self.pathEDagNetwork, loop=self.ctx.loop,
            autoUpdateDates=True
        )

        # Seeds
        self.dagSeedsMain = SeedsEDag(
            self.pathEdagSeedsMain, loop=self.ctx.loop,
            cipheredMeta=True
        )
        self.dagSeedsAll = MegaSeedsEDag(
            self.pathEdagSeedsAll, loop=self.ctx.loop,
            cipheredMeta=True
        )

        ensure(self.dagUser.load())
        await self.dagUser.loaded

        await self.dagChatChannels.load()

        await self.dagNetwork.load()

        await self.dagSeedsMain.load()
        await self.dagSeedsAll.load()

        await self.ipHandles.load()

        self.dagUser.dagCidChanged.connect(self.onDagChange)
        ensure(self.publishDag(allowOffline=True, reschedule=True))

        self.userWebsite = UserWebsite(
            self.dagUser,
            self,
            self.keyRootId,
            self.ctx.app.jinjaEnv,
            parent=self
        )

        await self.userWebsite.init()

        ensure(self.update())

        self._initialized = True
        self.userLogInfo('Initialization complete')

        ensure(self.sendChatLogin())
        ensure(self.ctx.app.manuals.importManuals(self))

    async def sendChatLogin(self):
        pass

    @ipfsOp
    async def cryptoInit(self, op):
        if not os.path.isfile(self.rsaPrivKeyPath) and \
                not os.path.isfile(self.rsaPubKeyPath):
            self.userLogInfo('Creating RSA keypair')

            privKey, pubKey = await self.rsaExec.genKeys()
            if privKey is None or pubKey is None:
                self.debug('RSA: keygen failed')
                return False

            try:
                async with aiofiles.open(self.rsaPrivKeyPath, 'w+b') as fd:
                    await fd.write(privKey)

                async with aiofiles.open(self.rsaPubKeyPath, 'w+b') as fd:
                    await fd.write(pubKey)
            except Exception as err:
                self.debug('RSA: could not save keys: {}'.format(str(err)))
                self.userLogInfo('Error while saving RSA keys!')
                return False
            else:
                os.chmod(self.rsaPrivKeyPath, 0o400)
                self.userLogInfo('Successfully created RSA keypair')

        if not await self.cryptoRegisterKeys():
            self.debug('RSA: failed to register keys')
            return False

        return True

    @ipfsOp
    async def cryptoRegisterKeys(self, op):
        self.userLogInfo('Registering keys')
        try:
            pubKey = await asyncReadFile(self.rsaPubKeyPath)
            if pubKey is None:
                self.debug('RSA: could not read public key')
                raise Exception('pubkey error')
            self.rsaPubKey = pubKey
        except Exception as e:
            self.debug('RSA: error while importing keys {}'.format(str(e)))
            return False
        else:
            self.rsaAgent = IpfsRSAAgent(self.rsaExec,
                                         self.rsaPubKey,
                                         self.rsaPrivKeyPath)
            op.setRsaAgent(self.rsaAgent)

            self.userInfo = UserProfileEDAG(
                self.pathProfileEDag, dagMetaHistoryMax=32,
                offline=True
            )
            await self.userInfo.load()

            if not self.userInfo.curIdentity:
                await self.createIpIdentifier(
                    iphandle=ipHandleGen(
                        getpass.getuser(),
                        'Earth',
                        peerId=op.ctx.node.id
                    )
                )

            if self.userInfo.curIdentity:
                # Load our IPID with low resolve timeout
                await self.ctx.app.ipidManager.load(
                    self.userInfo.personDid,
                    timeout=5,
                    localIdentifier=True
                )

            return True

    def ipIdentifierKeyName(self, idx: int):
        return 'galacteek.{0}.dids.{1}'.format(self.name, idx)

    async def onIdentitySwitch(self, identityUid, did):
        self.debug('Identity switched to DID {}'.format(did))

        if self.userInfo.curIdentity:
            # Load our IPID with low resolve timeout
            await self.ctx.app.ipidManager.load(
                did,
                timeout=5,
                localIdentifier=True
            )

    @ipfsOp
    async def createIpIdentifier(self, ipfsop,
                                 ipnsKey=None,
                                 peered=False,
                                 iphandle=None,
                                 updateProfile=False):
        if not iphandle:
            iphandle = ipHandleGen(
                'auto',
                'Earth',
                peerId=ipfsop.ctx.node.id
            )

        try:
            keysNames = await ipfsop.keysNames()
            useKeyIdx = 0
            for key in keysNames:
                ma = re.match(
                    r'galacteek.{0}.dids.([\d]+)$'.format(self.name),
                    key
                )
                if not ma:
                    continue

                num = int(ma.group(1))
                if num > useKeyIdx:
                    useKeyIdx = num + 1

            privKey, pubKey = await self.rsaExec.genKeys()

            ipid = await self.ctx.app.ipidManager.create(
                ipnsKey if ipnsKey else self.ipIdentifierKeyName(useKeyIdx),
                pubKeyPem=pubKey.decode()
            )
        except Exception as e:
            self.debug(str(e))
        else:
            didPrivKeyPath = os.path.join(
                self.ctx.app.cryptoDataLocation,
                'rsa_{0}_ipid_{1}_priv.key'.format(
                    self.name, ipid.ipnsKey))

            async with aiofiles.open(didPrivKeyPath, 'w+b') as fd:
                await fd.write(privKey)

            os.chmod(didPrivKeyPath, 0o400)

            self.userLogInfo('Generated IPID with DID: {did}'.format(
                did=ipid.did))

            if peered:
                uid, identity = await self.userInfo.createIdentityPeered(
                    iphandle=iphandle,
                    personDid=ipid.did
                )
            else:
                uid, identity = await self.userInfo.createIdentity(
                    iphandle=iphandle,
                    personDid=ipid.did,
                    setAsCurrent=True,
                )

            await self.ipIdentifierInit(ipid)

            ensure(ipid.publish())

            if updateProfile is True:
                await self.identityChanged.emit(
                    self.userInfo.root['currentIdentityUid'],
                    self.userInfo.curIdentity['personDid']
                )

            return ipid

    @ipfsOp
    async def ipIdentifierInit(self, ipfsop, ipid: IPIdentifier):
        # Register the blog as an IP service on the DID
        blogPath = IPFSPath(joinIpns(self.keyRootId)).child('blog')
        await ipid.addServiceRaw({
            'id': ipid.didUrl(path='/blog'),
            'type': IPService.SRV_TYPE_DWEBBLOG,
            'serviceEndpoint': blogPath.ipfsUrl
        }, publish=False)

        # Register the Atom feed as an IP service on the DID
        feedPath = IPFSPath(joinIpns(self.keyRootId)).child('dfeed.atom')
        await ipid.addServiceRaw({
            'id': ipid.didUrl(path='/feed'),
            'type': IPService.SRV_TYPE_ATOMFEED,
            'serviceEndpoint': feedPath.ipfsUrl,
            'description': 'Dweb Atom feed'
        }, publish=False)

        await ipid.addServiceCollection('default')

    @ipfsOp
    async def rsaEncryptSelf(self, op, data, offline=False):
        return await self.rsaAgent.storeSelf(data, offline=offline)

    @ipfsOp
    async def rsaDecryptIpfsObj(self, op, cid):
        return await self.rsaAgent.decryptIpfsObject(cid)

    async def __rsaReadPrivateKey(self):
        log.debug('RSA: reading private key')
        return await asyncReadFile(self.rsaPrivKeyPath)

    def onUserInfoChanged(self):
        ensure(self.update())

    def onUserNameChanged(self):
        ensure(self.publishProfile())

    def onOrbitalConfigChanged(self):
        pass

    @ipfsOp
    async def reconfigureOrbit(self, ipfsop):
        await ipfsop.ctx.orbitConnector.reconfigure()

    def syncOrbital(self):
        self.orbitalCfgFile.set(self.orbitalCfgMap.data)
        self.orbitalCfgFile.changed.emit()

    async def orbitalSetup(self, conn):
        conn.useConfigMap(OrbitConfigMap(defaultOrbitConfigMap))

        self.orbitalCfgFile = QJSONFile(os.path.join(
            self.ctx.app.dataLocation, 'orbital.profile.json'))
        self.orbitalCfgMap = OrbitConfigMap(self.orbitalCfgFile.root)
        conn.useConfigMap(self.orbitalCfgMap)

        self.orbitalCfgMap.notifier.changed.connect(
            lambda: self.syncOrbital())

        userNs = self.userInfo.uid

        self.orbitalDbProfile = conn.database(userNs,
                                              'profile', dbtype='keyvalue')

        if not self.orbitalCfgMap.hasDatabase(userNs, 'profile'):
            self.orbitalCfgMap.newDatabase(
                self.orbitalDbProfile.ns,
                self.orbitalDbProfile.dbname,
                self.orbitalDbProfile.dbtype
            )
            await self.orbitalDbProfile.create()
            self.orbitalCfgFile.changed.emit()
            await self.reconfigureOrbit()

        await self.reconfigureOrbit()
        await self.orbitalDbProfile.open()

    async def publishProfile(self):
        if self.ctx.inOrbit:
            conn = self.ctx.orbitConnector
            log.debug('Publishing username {0}'.format(self.userInfo.username))

            usernames = await conn.usernamesList()

            logUser.debug('Existing usernames in database: {users}'.format(
                users=','.join(usernames)))

            if self.userInfo.username not in usernames:
                await conn.dbUsernames.add({
                    'name': self.userInfo.username
                })

            entry = await self.orbitalDbProfile.get(self.userInfo.username)
            if not entry:
                await self.orbitalDbProfile.set(
                    self.userInfo.username, self.userInfo.root['userinfo'])

    def onDagChange(self):
        ensure(self.publishDag())

    @ipfsOp
    async def publishDag(self, op, allowOffline=False, reschedule=False):
        if not self.dagUser.dagCid:
            self.debug('DAG CID not set yet ?')
            return

        self.debug('Publishing profile DAG with CID {}'.format(
            self.dagUser.dagCid))

        result = await op.publish(self.dagUser.dagCid,
                                  key=self.keyRootId,
                                  allow_offline=allowOffline,
                                  cache='always',
                                  cacheOrigin='profile',
                                  resolve=True,
                                  lifetime='48h')

        if result is None:
            self.debug('DAG publish failed')
        else:
            self.debug('DAG publish success: {}'.format(result))

        if reschedule is True:
            self.debug('Rescheduling user DAG publish')
            ensureLater(60 * 5,
                        self.publishDag, reschedule=reschedule,
                        allowOffline=allowOffline)

    async def tmplRender(self, tmpl, **kw):
        """
        Render an HTML template (jinja)
        """
        return await render.ipfsRender(self.ctx.app.jinjaEnv,
                                       tmpl,
                                       profile=self,
                                       dag=self.dagUser.dagRoot,
                                       siteIpns=self.keyRootId,
                                       **kw)

    async def tmplRenderContained(self, tmpl, **kw):
        return await render.ipfsRenderContained(self.ctx.app.jinjaEnv,
                                                tmpl,
                                                profile=self,
                                                dag=self.dagUser.dagRoot,
                                                siteIpns=self.keyRootId,
                                                **kw)

    @ipfsOp
    async def update(self, op):
        """
        Update the user's DAG
        """

        if not self.dagUser:
            return

        await self.dagUser.loaded

        if await self.userWebsite.edag.neverUpdated():
            # First build
            await self.userWebsite.update()

    @ipfsOp
    async def storeHashmarksFromJson(self, ipfsop, senderPeerId, marksJson):
        await self.sharedHManager.store(ipfsop, senderPeerId, marksJson)

    @ipfsOp
    async def storeHashmarks(self, ipfsop, senderPeerId, ipfsMarks):
        await self.sharedHManager.store(ipfsop, senderPeerId, ipfsMarks.root)

    @ipfsOp
    async def onQrImageEncoded(self, ipfsop,
                               encrypt: bool,
                               imgPath: str):
        basename = os.path.basename(imgPath)
        file = QFile(imgPath)

        if encrypt:
            if not file.open(QIODevice.ReadOnly):
                return
            data = file.readAll().data()
            entry = await self.rsaEncryptSelf(data)
        else:
            entry = await ipfsop.addPath(imgPath, offline=True)

        if entry:
            # Link it, open it
            dst = self.pathQrCodesEncrypted if encrypt is True else \
                self.pathQrCodes
            await ipfsop.filesLink(entry, dst, name=basename)
            await self.ctx.app.resourceOpener.open(entry['Hash'])

    @ipfsOp
    async def onWebPageSaved(self, ipfsop, entry, pageTitle):
        if not pageTitle:
            pageTitle = 'Unknown.{}'.format(int(time.time()))

        await ipfsop.filesLink(entry, self.pathWebPages, name=pageTitle)

    def createMfsMenu(self, title='MFS', parent=None):
        mfsMenu = QMenu(title, parent)

        for item in self.filesModel.fsCore:
            icon = item.icon()
            action = QAction(icon, item.text(), self)
            action.setData(item)
            mfsMenu.addAction(action)
            mfsMenu.addSeparator()

        return mfsMenu

    def edagMetadataPath(self, name):
        return os.path.join(
            self.pathEDags, '{0}.edag.json'.format(name))

    def edagPyramidMetadataPath(self, name):
        return os.path.join(
            self.pathEDagsPyramids, '{0}.edag.json'.format(name))
