import os
import os.path
import uuid
import asyncio
import time
from os import urandom
from datetime import datetime

import aiofiles

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtCore import QFile
from PyQt5.QtCore import QIODevice
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QAction

from galacteek import log
from galacteek import logUser
from galacteek import ensure

from galacteek.ipfs import ipfsOpFn
from galacteek.ipfs.mutable import MutableIPFSJson, CipheredIPFSJson
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.encrypt import IpfsRSAAgent
from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek.ipfs.pubsub.messages import ChatRoomMessage

from galacteek.core import isoformat
from galacteek.core.asynclib import asyncReadFile
from galacteek.core.orbitdb import OrbitConfigMap
from galacteek.core.orbitdbcfg import defaultOrbitConfigMap
from galacteek.core.jsono import QJSONFile
from galacteek.core.models.mfs import createMFSModel
from galacteek.core.ipfsmarks import IPFSMarks

from galacteek.core.userdag import UserDAG
from galacteek.core.userdag import UserWebsite

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


class UserInfos(CipheredIPFSJson):
    GENDER_MALE = 0
    GENDER_FEMALE = 1
    GENDER_UNSPECIFIED = -1

    usernameChanged = pyqtSignal()
    changed = pyqtSignal()

    def initObj(self):
        uid = str(uuid.uuid4())

        return {
            'userinfo': {
                'username': uid,
                'firstname': '',
                'lastname': '',
                'altname': '',
                'nickname': '',
                'gender': -1,
                'org': '',
                'email': '',
                'country': {
                    'code': '',
                    'name': '',
                },
                'city': '',
                'birthdate': '',
                'birthplace': '',
                'occupation': '',
                'telephone': '',
                'langs': [],
                'avatar': {
                    'cid': '',
                },
                'bio': '',
                'motto': '',
                'crypto': {
                    'rsa': {},
                    'gpg': {},
                },
                'resources': [],
                'peerid': '',
                'date': {
                    'created': isoformat(datetime.now()),
                    'modified': isoformat(datetime.now()),
                },
                'uid': uid,
                'locked': False,
                'schemav': 1,
            }
        }

    @property
    def usernameSet(self):
        return self.uid != self.username

    @property
    def uid(self):
        return self.parser.traverse('userinfo.uid')

    @property
    def peerid(self):
        return self.parser.traverse('userinfo.peerid')

    @property
    def avatarCid(self):
        return self.parser.traverse('userinfo.avatar.cid')

    @property
    def bio(self):
        return self.parser.traverse('userinfo.bio')

    @property
    def username(self):
        return self.parser.traverse('userinfo.username')

    @property
    def firstname(self):
        return self.parser.traverse('userinfo.firstname')

    @property
    def lastname(self):
        return self.parser.traverse('userinfo.lastname')

    @property
    def email(self):
        return self.parser.traverse('userinfo.email')

    @property
    def gender(self):
        return self.parser.traverse('userinfo.gender')

    @property
    def org(self):
        return self.parser.traverse('userinfo.org')

    @property
    def city(self):
        return self.parser.traverse('userinfo.city')

    @property
    def countryName(self):
        return self.parser.traverse('userinfo.country.name')

    @property
    def countryCode(self):
        return self.parser.traverse('userinfo.country.code')

    @property
    def locked(self):
        return self.parser.traverse('userinfo.locked')

    @property
    def identToken(self):
        return self.parser.traverse('userinfo.identtoken')

    @property
    def schemaVersion(self):
        return self.parser.traverse('userinfo.schemav')

    @property
    def objHash(self):
        if self.curEntry:
            return self.curEntry['Hash']

    def setAvatarCid(self, cid):
        if self.locked:
            return
        self.root['userinfo']['avatar']['cid'] = cid
        self.updateModifiedDate()
        self.changed.emit()

    def setCountryInfo(self, name, code):
        if self.locked:
            return
        sec = self.root['userinfo']['country']
        sec['name'] = name
        sec['code'] = code
        self.updateModifiedDate()
        self.changed.emit()

    def setInfos(self, **kw):
        if self.locked:
            return
        for key, val in kw.items():
            if key not in self.root['userinfo'].keys():
                continue
            self.root['userinfo'][key] = val
        self.updateModifiedDate()
        self.changed.emit()

    def updateModifiedDate(self):
        self.root['userinfo']['date']['modified'] = isoformat(datetime.now())

    def updateIdentToken(self):
        token = self.root['userinfo'].get('identtoken', None)
        if not token:
            self.root['userinfo']['identtoken'] = urandom(128).hex()
            self.changed.emit()

    def setLock(self, lock=False):
        self.root['userinfo']['locked'] = lock
        self.changed.emit()

    def valid(self):
        return True


class ProfileError(Exception):
    pass


class SharedHashmarksManager(QObject):
    hashmarksLoaded = pyqtSignal(IPFSMarks)

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
            await asyncio.sleep(180)

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
                self.hashmarksLoaded.emit(marks)
                self._loaded.append(marksHash)
            except BaseException as err:
                log.debug('Could not load hashmarks from CID {0}: {1}'.format(
                    marksHash, str(err)))
            else:
                logUser.info('Loaded hashmarks from peer {0}'.format(uid))
                await asyncio.sleep(2)

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
                marks._root = marksJson
                marks.changed.emit()
                self._state[sender] = marks
            else:
                marks = self._state[sender]
                marks._root = marksJson
                marks.changed.emit()

        await asyncio.sleep(1)


class UserProfile(QObject):
    """
    User profile object
    """

    P_FILES = 'files'

    qrImageEncoded = pyqtSignal(bool, str)
    webPageSaved = pyqtSignal(dict, str)

    def __init__(self, ctx, name, rootDir):
        super(UserProfile, self).__init__()

        self._ctx = ctx
        self._name = name
        self._rootDir = rootDir
        self._initialized = False

        self.keyRoot = 'galacteek.{}.root'.format(self.name)
        self.keyRootId = None

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
        self.orbitalConfigMfs = None
        self.orbitalCfgMap = None

        self.rsaAgent = None
        self.sharedHManager = SharedHashmarksManager(self)

        self.qrImageEncoded.connect(self.onQrImageEncoded)
        self.webPageSaved.connect(self.onWebPageSaved)

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
            self.pathEncryptedFiles
        ]

    @property
    def pathFiles(self):
        return os.path.join(self.root, self.P_FILES)

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
    def pathUserDagMeta(self):
        return os.path.join(self.pathData, 'dag.main')

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

        self.userLogInfo('Initializing crypto')

        if not await self.cryptoInit():
            self.userLogInfo('Error while initializing crypto')
            raise ProfileError('Crypto init failed')

        key = await ipfsop.keyFind(self.keyRoot)
        if key is not None:
            self.keyRootId = key.get('Id', None)
        else:
            self.userLogInfo('Generating main IPNS key')
            result = await ipfsop.keyGen(self.keyRoot)
            self.keyRootId = result.get('Id', None)

        self.debug('IPNS key({0}): {1}'.format(self.keyRoot, self.keyRootId))

        if self.userInfo.avatarCid == '' and self.ctx.hasRsc('ipfs-logo-ice'):
            self.userInfo.setAvatarCid(
                self.ctx.resources['ipfs-logo-ice']['Hash'])

        if self.userInfo.peerid == '':
            self.userInfo.root['userinfo']['peerid'] = self.ctx.node.id
            self.userInfo.changed.emit()

        if await ipfsop.hasDagCommand():
            self.userLogInfo('Loading DAG ..')
            self._dagUser = UserDAG(self.pathUserDagMeta, loop=self.ctx.loop)

            ensure(self.dagUser.load())
            await self.dagUser.loaded

            self.dagUser.dagCidChanged.connect(self.onDagChange)
            ensure(self.publishDag())

            self.userWebsite = UserWebsite(
                self.dagUser,
                self,
                self.keyRootId,
                self.ctx.app.jinjaEnv,
                parent=self
            )

            await self.userWebsite.init()

            ensure(self.update())
            self.userLogInfo('Loaded')
        else:
            self.debug('DAG api not available !')

        ensure(self.sendChatLogin())

        self._initialized = True
        self.userLogInfo('Initialization complete')
        self.userInfo.changed.connect(self.onUserInfoChanged)
        self.userInfo.usernameChanged.connect(self.onUserNameChanged)

        ensure(self.sharedHManager.scanningTask())
        ensure(self.ctx.app.manuals.importManuals(self))

    async def sendChatLogin(self):
        msg = ChatRoomMessage.make(
            self.userInfo.username,
            ChatRoomMessage.CHANNEL_GENERAL,
            'logged in')
        await self.ctx.pubsub.send(TOPIC_CHAT, msg)

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
            #
            # Tough decision here .. first mechanism tried for publishing the
            # peer's public key payload was to import the PEM key in the
            # repository and transmit the CID, which is neat and handy (other
            # peers just pin/fetch the key..) ATM embedding the key's payload
            # in the userinfo offers some advantages and we can always use
            # another system later on
            #
            self.rsaAgent = IpfsRSAAgent(self.rsaExec,
                                         self.rsaPubKey,
                                         self.rsaPrivKeyPath)
            op.setRsaAgent(self.rsaAgent)

            self.userLogInfo('Loading user information')
            self.userInfo = UserInfos(self.pathUserInfo, self.rsaAgent)

            ensure(self.userInfo.load())
            await self.userInfo.evLoaded.wait()
            self.userInfo.updateIdentToken()

            rsaSection = self.userInfo.root['userinfo']['crypto'].setdefault(
                'rsa', {})
            prevPem = rsaSection.get('pubkeypem', None)
            rsaSection['pubkeypem'] = self.rsaPubKey.decode()

            if rsaSection['pubkeypem'] != prevPem:
                self.userInfo.changed.emit()

            return True

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
    async def publishDag(self, op):
        if not self.dagUser.dagCid:
            self.debug('DAG CID not set yet ?')
            return

        self.debug('Publishing DAG CID {}'.format(self.dagUser.dagCid))

        result = await op.publish(self.dagUser.dagCid, key=self.keyRoot,
                                  allow_offline=True, lifetime='48h')

        if result is None:
            self.debug('DAG publish failed: {}'.format(result))
        else:
            self.debug('DAG publish success: {}'.format(result))

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
    async def storeHashmarks(self, ipfsop, senderPeerId, marksJson):
        await self.sharedHManager.store(ipfsop, senderPeerId, marksJson)

    def onQrImageEncoded(self, encrypt, imgPath):
        @ipfsOpFn
        async def storeQrImage(ipfsop, encrypt, path):
            basename = os.path.basename(path)
            file = QFile(path)

            if encrypt:
                if not file.open(QIODevice.ReadOnly):
                    return
                data = file.readAll().data()
                entry = await self.rsaEncryptSelf(data)
            else:
                entry = await ipfsop.addPath(path, offline=True)

            if entry:
                # Link it, open it
                dst = self.pathQrCodesEncrypted if encrypt is True else \
                    self.pathQrCodes
                await ipfsop.filesLink(entry, dst, name=basename)
                ensure(self.ctx.app.resourceOpener.open(entry['Hash']))

        ensure(storeQrImage(encrypt, imgPath))

    def onWebPageSaved(self, entry, title):
        @ipfsOpFn
        async def linkWebPage(ipfsop, wEntry, pageTitle):
            if not pageTitle:
                pageTitle = 'Unknown.{}'.format(int(time.time()))

            await ipfsop.filesLink(wEntry, self.pathWebPages, name=pageTitle)

        ensure(linkWebPage(entry, title))

    def createMfsMenu(self, title='MFS', parent=None):
        mfsMenu = QMenu(title, parent)

        for item in self.filesModel.fsCore:
            icon = item.icon()
            action = QAction(icon, item.text(), self)
            action.setData(item)
            mfsMenu.addAction(action)
            mfsMenu.addSeparator()

        return mfsMenu
