import asyncio
import functools
import weakref
import aiorwlock
import os.path
import orjson
import re

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QToolButton

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QSortFilterProxyModel
from PyQt5.QtCore import QRegExp
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal
from PyQt5.QtCore import QVariant

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtGui import QStandardItem

from PyQt5.QtWidgets import QAbstractItemView

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek.ipfs.pubsub.messages.chat import ChatRoomMessage
from galacteek.ipfs.pubsub.messages.chat import UserChannelsListMessage
from galacteek.ipfs.pubsub.srvs.chat import PSEncryptedChatChannelService

from galacteek.core import doubleUid4
from galacteek.core import uid4
from galacteek.core.ps import makeKeyChatChannel
from galacteek.core.ps import keyChatChanList
from galacteek.core.ps import psSubscriber
from galacteek.core.ps import keyChatChanUserList
from galacteek.core.ps import makeKeyPubChatTokens
from galacteek.core.ps import mSubscriber
from galacteek.core.ps import gHub
from galacteek.core.chattokens import PubChatTokensManager
from galacteek.core.chattokens import ChatToken

from galacteek.core import SingletonDecorator

from galacteek.dweb.markdown import markitdown
from galacteek.dweb.page import IPFSPage
from galacteek.dweb.page import BaseHandler
from galacteek.dweb.page import GalacteekHandler

from galacteek.core import datetimeNow
from galacteek import ensure
from galacteek import ensureLater
from galacteek import log
from galacteek import partialEnsure
from galacteek.core.modelhelpers import UneditableItem

from .dwebspace import WS_PEERS
from .peers import peerToolTip
from .helpers import getIcon
from .helpers import inputTextCustom
from .helpers import messageBox
from .helpers import runDialogAsync
from .widgets import GalacteekTab
from .widgets import PopupToolButton
from .widgets import IPFSWebView
from .widgets import IconSelector
from .i18n import iChat
from .i18n import iChatMessageNotification

from . import ui_chatchannelslist
from . import ui_chatchannelnew
from . import ui_privchatchannelnew
from . import ui_chatroom


@SingletonDecorator
class ChatChannels(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.lock = asyncio.Lock()
        self.channelWidgets = weakref.WeakValueDictionary()
        self.userListRev = uid4()

        self.pubTokensManager = PubChatTokensManager()

        ensure(self.sendChannelsStatus())

    @ipfsOp
    async def cnCountByChannel(self, ipfsop, channel):
        mChatService = ipfsop.ctx.pubsub.byTopic(TOPIC_CHAT)
        pList = [p async for p, _ in mChatService.peersByChannel(channel)]
        return len(pList)

    @ipfsOp
    async def createPublicChannel(self, ipfsop, channel):
        dagChannels = ipfsop.ctx.currentProfile.dagChatChannels
        dagChannels.registerPublic(channel)

    @ipfsOp
    async def createPrivateChannel(self, ipfsop, channel):
        dagChannels = ipfsop.ctx.currentProfile.dagChatChannels
        dagChannels.registerPrivate(channel)

    @ipfsOp
    async def leaveChannel(self, ipfsop, channel, psService):
        await psService.stop()

        if channel in self.channelWidgets:
            del self.channelWidgets[channel]

    async def sendChannelsStatus(self):
        pubChannels = {}
        pubChannels = []

        for chan, _w in self.channelWidgets.items():
            pubChannels.append({
                'tokenSigMethod': 'rsa',
                'sessionJwsCid': _w.psService.jwsTokenCid
            })

        userChannelsMsg = UserChannelsListMessage.make(
            self.userListRev, pubChannels)

        gHub.publish(keyChatChanList, userChannelsMsg)
        ensureLater(10, self.sendChannelsStatus)

    @ipfsOp
    async def joinChannel(self, ipfsop, channel, chanSticky=False):
        if channel in self.channelWidgets.keys():
            return self.channelWidgets[channel]

        cAgent = ipfsop.curve25519Agent

        pubKeyCid = await cAgent.pubKeyCid()

        chatToken = await ChatToken.make(ipfsop, channel, pubKeyCid,
                                         encType='curve25519')
        log.debug(chatToken.pretty())

        # Create the JWS and import it without pinning
        jwsToken = await ipfsop.rsaAgent.jwsTokenObj(
            orjson.dumps(chatToken.data).decode())
        jwsTokenEntry = await ipfsop.addJson(jwsToken, pin=False)

        # Create an aiopubsub key and start the pubsub service
        key = makeKeyChatChannel(channel)
        service = PSEncryptedChatChannelService(
            ipfsop.ctx,
            self.app.ipfsClient,
            channel,
            chatToken.psTopic,
            jwsTokenEntry['Hash'],
            cAgent.privKey,
            key,
            scheduler=self.app.scheduler
        )

        ipfsop.ctx.pubsub.reg(service)
        await service.start()

        self.userListRev = uid4()

        # Create the chatroom widget
        self.channelWidgets[channel] = w = ChatRoomWidget(
            channel, service, self.app.mainWindow,
            sticky=chanSticky
        )

        ensure(w.startHeartbeatTask())
        ensureLater(3, w.sendStatusJoin)
        return self.channelWidgets[channel]


class JoinChannelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.chans = ChatChannels()
        self.ui = ui_chatchannelslist.Ui_ChannelsListDialog()
        self.ui.setupUi(self)
        self.ui.joinButton.clicked.connect(self.onJoinClicked)
        self.ui.cancelButton.clicked.connect(
            functools.partial(self.done, 1))

        self.channelsModel = QStandardItemModel()
        self.channelsModel.setHorizontalHeaderLabels(['Channel', 'Connected'])
        self.channelsProxyModel = QSortFilterProxyModel(self)
        self.channelsProxyModel.setSourceModel(self.channelsModel)
        self.channelsProxyModel.setFilterKeyColumn(0)
        self.channelsProxyModel.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.ui.channelsView.setModel(self.channelsProxyModel)
        self.ui.channelsView.doubleClicked.connect(
            lambda idx: self.onJoinClicked())
        self.ui.channelsView.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.ui.searchLine.textChanged.connect(self.onApplySearch)

    @ipfsOp
    async def initDialog(self, ipfsop):
        dagChannels = ipfsop.ctx.currentProfile.dagChatChannels
        for channel in dagChannels.channels:
            self.channelsModel.appendRow([
                UneditableItem(channel),
                UneditableItem(
                    str(await self.chans.cnCountByChannel(channel)))
            ])
            await ipfsop.sleep()

    def onApplySearch(self):
        self.channelsProxyModel.setFilterRegExp(self.ui.searchLine.text())

    def onJoinClicked(self):
        try:
            idx = self.ui.channelsView.selectionModel().selectedRows(0).pop()
        except Exception:
            return

        chan = self.channelsProxyModel.data(idx, Qt.DisplayRole)
        if chan:
            ensure(self.onJoinChannel(chan))

        self.done(1)

    @ipfsOp
    async def onJoinChannel(self, ipfsop, channel):
        log.info(f'Joining channel: {channel}')

        widget = await self.chans.joinChannel(channel)
        self.app.mainWindow.registerTab(
            widget, name=channel,
            icon=getIcon('qta:mdi.chat-outline'),
            current=True,
            workspace=WS_PEERS
        )


class PublicChatChannelNewDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.chans = ChatChannels()
        self.ui = ui_chatchannelnew.Ui_ChatChannelNewDialog()
        self.ui.setupUi(self)
        self.ui.buttonBox.accepted.connect(self.onAccepted)
        self.ui.buttonBox.rejected.connect(functools.partial(
            self.done, 1))

        regexp1 = QRegExp(r'[#A-Za-z0-9-_]+')
        self.ui.channelName.setValidator(QRegExpValidator(regexp1))
        self.ui.channelName.setMaxLength(64)

    def onAccepted(self):
        channel = self.ui.channelName.text().strip()

        if not channel.startswith('#'):
            return messageBox('Channel name should start with a #')

        ensure(self.chans.createPublicChannel(channel))
        self.done(1)


class PrivateChatChannelNewDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.chans = ChatChannels()
        self.iconSel = IconSelector()

        self.ui = ui_privchatchannelnew.Ui_NewPrivateChatChannelDialog()
        self.ui.setupUi(self)
        self.ui.buttonBox.accepted.connect(self.onAccepted)
        self.ui.buttonBox.rejected.connect(functools.partial(
            self.done, 1))

        self.ui.gridLayout.addWidget(self.iconSel, 3, 1)

        regexp1 = QRegExp(r'[#A-Za-z0-9-_]+')
        self.ui.channelName.setValidator(QRegExpValidator(regexp1))
        self.ui.channelName.setMaxLength(64)

    def onAccepted(self):
        ensure(self.createPrivateChannel())

    @ipfsOp
    async def createPrivateChannel(self, ipfsop):
        dagChannels = ipfsop.ctx.currentProfile.dagChatChannels
        name = self.ui.channelName.text().strip()
        descr = self.ui.channelDescription.text().strip()

        uid = doubleUid4()
        eccPriv, eccPub = await ipfsop.ctx.eccExec.genKeys()

        privPath = os.path.join(
            self.app.eccChatChannelsDataLocation,
            'ecc_channel_{uid}.priv.key'
        )

        with open(privPath, 'w+t') as fd:
            fd.write(eccPriv)

        eccEntry = await ipfsop.addString(eccPub)

        channel = await ipfsop.dagPut({
            'channel': {
                'uid': uid,
                'name': name,
                'description': descr,
                'icon': {
                    '/': self.iconSel.iconCid
                },
                'eccPubKey': {
                    '/': eccEntry['Hash']
                }
            }
        })

        path = IPFSPath(channel)
        dagChannels.registerPrivate(path.objPath)
        self.done(1)


class ChatCenterButton(PopupToolButton):
    def __init__(self, *args, **kw):
        super().__init__(
            icon=getIcon('chat.png'),
            mode=QToolButton.InstantPopup,
            *args, **kw
        )

        self.setToolTip(iChat())

        self.app = QApplication.instance()
        self.menu.addAction(
            getIcon('qta:mdi.chat'),
            'Create public channel',
            self.onCreateChannel
        )
        self.menu.addSeparator()

        if 0:
            self.menu.addAction(
                getIcon('qta:mdi.chat'),
                'Create private channel',
                self.onCreatePrivateChannel
            )
            self.menu.addSeparator()

        self.menu.addAction(
            getIcon('qta:mdi.chat'),
            'Join channel',
            self.onJoinChannelFromList
        )

        self.chans = ChatChannels()

    def onJoinChannelFromList(self):
        ensure(runDialogAsync(JoinChannelDialog))

    @ipfsOp
    async def onShowChannels(self, ipfsop):
        dagChannels = ipfsop.ctx.currentProfile.dagChatChannels
        self.chanMenu.clear()

        for channel in dagChannels.channels:
            self.chanMenu.addAction(
                getIcon('qta:mdi.chat'),
                channel, partialEnsure(
                    self.chans.onJoinChannel,
                    channel
                )
            )

    def onCreateChannel(self):
        ensure(runDialogAsync(PublicChatChannelNewDialog))

    def onCreatePrivateChannel(self):
        ensure(runDialogAsync(PrivateChatChannelNewDialog))

    def old(self):
        channel = inputTextCustom(label='Channel name')
        if channel:
            ensure(self.chans.createPublicChannel(channel))


class ParticipantItem(QStandardItem):
    pass


class ParticipantsModel(QStandardItemModel):
    def flags(self, index):
        return Qt.ItemFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

    def pData(self, row, col):
        return self.data(
            self.index(
                row,
                col
            ),
            Qt.DisplayRole
        )

    def data(self, index, role):
        if role == Qt.DecorationRole:
            item = self.itemFromIndex(index)
            if isinstance(item, ParticipantItem):
                ctx = item.peerCtx()
                if ctx:
                    return ctx.avatarPixmapScaled(32, 32)

        return super().data(index, role)


class ChatHandler(BaseHandler):
    chatMsgReceived = pyqtSignal(QVariant)
    chatJoinLeftReceived = pyqtSignal(QVariant)
    chatMsgAttachments = pyqtSignal(str, QVariant)

    @pyqtSlot(str)
    def sendMessage(self, msg):
        ensure(self.chatWidget.sendMessage(msg))


class ChatRoomPage(IPFSPage):
    def setPermissions(self):
        from PyQt5.QtWebEngineWidgets import QWebEngineSettings

        self.settings().setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls,
            True
        )
        self.settings().setAttribute(
            QWebEngineSettings.FullScreenSupportEnabled,
            True
        )

    def onPermissionRequest(self, url, feature):
        from PyQt5.QtWebEngineWidgets import QWebEnginePage

        if 0:
            self.setFeaturePermission(
                QUrl('file:/chatroom'),
                QWebEnginePage.MediaAudioVideoCapture,
                QWebEnginePage.PermissionGrantedByUser
            )

    def onFullScreenRequest(self, request):
        request.accept()


class ChatWebView(IPFSWebView):
    def __init__(self, chatWidget):
        super().__init__(parent=chatWidget)

        self.chatWidget = chatWidget

        self._page = ChatRoomPage('chatroom.html',
                                  url=QUrl('file:/chatroom'),
                                  parent=self,
                                  navBypassLinks=True)

        self.hChat = ChatHandler(self)
        self.hChat.chatWidget = chatWidget
        self._page.register('chatroom', self.hChat)
        self._page.register('galacteek', GalacteekHandler(self))
        self.setPage(self._page)


class ChatRoomWidget(GalacteekTab):
    def __init__(self, channel, psService, gWindow, sticky=False):
        super(ChatRoomWidget, self).__init__(gWindow, sticky=sticky)

        self.lock = aiorwlock.RWLock()
        self.chans = ChatChannels()

        mSubscriber.add_async_listener(
            keyChatChanUserList, self.onChatChanUserList)
        mSubscriber.add_async_listener(
            makeKeyPubChatTokens(channel), self.onChatTokenMessage)

        self.participantsModel = ParticipantsModel(self)
        self.participantsModel.setHorizontalHeaderLabels(
            ['Token', 'SpaceHandle']
        )

        self.chatView = ChatWebView(self)

        self.channel = channel
        self.subscriber = psSubscriber(psService.topic)
        self.psService = psService
        self.subscriber.add_async_listener(
            self.psService.psKey, self.onChatMessageReceived
        )
        self.chatWidget = QWidget()
        self.vLayout.addWidget(self.chatWidget)

        self.ui = ui_chatroom.Ui_Form()
        self.ui.setupUi(self.chatWidget)
        self.ui.hLayoutTop.addWidget(self.chatView)

        self.ui.hideUsersButton.clicked.connect(self.onHideUsers)

        self.ui.usersView.setModel(self.participantsModel)
        self.ui.usersView.hideColumn(0)

    def onHideUsers(self):
        self.ui.usersView.setVisible(not self.ui.usersView.isVisible())

    def focusMessage(self):
        self.ui.message.setFocus(Qt.OtherFocusReason)

    async def onTabChanged(self):
        self.setTabIcon(getIcon('qta:mdi.chat-outline'))

    async def participantsHandles(self):
        return [p['handle'] for p in await self.participantsData()]

    async def participantsData(self):
        async with self.lock.reader_lock:
            for row in range(self.participantsModel.rowCount()):
                yield {
                    'handle': self.participantsModel.pData(row, 1),
                    'tokencid': self.participantsModel.pData(row, 0),
                    'row': row
                }

    @ipfsOp
    async def onChatTokenMessage(self, ipfsop, key, message):
        tokenCid, status = message

        if status == 1:
            idxHandle, _ = self.participantIdxByToken(tokenCid)
            if not idxHandle:
                return
            self.participantsModel.removeRow(idxHandle.row())

        if status == 0 and 0:
            token = await self.chans.pubTokensManager.tokenGet(tokenCid)
            if not token:
                return

            piCtx = ipfsop.ctx.peers.getByPeerId(token.peerId)
            if not piCtx:
                return

            idxHandle, _ = self.participantIdxByToken(token.cid)
            if not idxHandle:
                self.addParticipant(piCtx, token)

    @ipfsOp
    async def onChatChanUserList(self, ipfsop, key, message):
        chan, peerList = message

        if chan != self.channel:
            return

        for peer, token in peerList:
            piCtx = ipfsop.ctx.peers.getByPeerId(peer)
            if not piCtx:
                continue

            idxHandle, _ = self.participantIdxByToken(token.cid)
            if not idxHandle:
                self.addParticipant(piCtx, token)

    def participantIdxByToken(self, tokenCid):
        try:
            idxList = self.participantsModel.match(
                self.participantsModel.index(0, 0, QModelIndex()),
                Qt.DisplayRole,
                tokenCid,
                -1,
                Qt.MatchFixedString | Qt.MatchWrap | Qt.MatchRecursive
            )

            idx = idxList.pop()

            sibling = self.participantsModel.sibling(
                idx.row(), 1,
                self.participantsModel.invisibleRootItem().index()
            )
            return sibling, idx
        except Exception:
            return None, None

    def participantIdx(self, handle):
        try:
            idxList = self.participantsModel.match(
                self.participantsModel.index(0, 1, QModelIndex()),
                Qt.DisplayRole,
                handle,
                -1,
                Qt.MatchFixedString | Qt.MatchWrap | Qt.MatchRecursive
            )

            idx = idxList.pop()

            sibling = self.participantsModel.sibling(
                idx.row(), 0,
                self.participantsModel.invisibleRootItem().index()
            )
            return idx, sibling
        except Exception:
            return None, None

    def addParticipant(self, piCtx, token):
        itemHandle = ParticipantItem(piCtx.spaceHandle.short)
        itemHandle.setToolTip(peerToolTip(piCtx))
        itemHandle.peerCtx = weakref.ref(piCtx)
        itemToken = QStandardItem(token.cid)

        self.participantsModel.invisibleRootItem().appendRow(
            [itemToken, itemHandle]
        )

    async def userHeartbeat(self, message):
        return

    async def userLeft(self, message):
        await self.removeUser(message.peerCtx.spaceHandle.short)
        await self.chans.pubTokensManager.tokenDestroy(message.jwsTokenCid)

    async def removeUser(self, handle):
        idxHandle, _ = self.participantIdx(handle)
        if idxHandle:
            self.participantsModel.removeRow(idxHandle.row())

    @ipfsOp
    async def onChatMessageReceived(self, ipfsop, key, hubMessage):
        sender, message = hubMessage
        now = datetimeNow()
        fromUs = (message.peerCtx.peerId == ipfsop.ctx.node.id)

        defAvatar = IPFSPath(ipfsop.ctx.resources['ipfs-cube-64'])

        avatarPath = str(message.peerCtx.avatarPath) if \
            message.peerCtx.avatarPath else defAvatar.objPath

        if message.command == ChatRoomMessage.COMMAND_HEARTBEAT:
            # await self.userHeartbeat(message)
            return

        if message.command == ChatRoomMessage.COMMAND_MSGMARKDOWN:
            if not isinstance(message.messageBody, str):
                return

            if len(message.messageBody) not in range(1, 768):
                return

            if not self.isVisible():
                self.setTabIcon(getIcon('chat-active.png'))
                self.tabActiveNotify()
            else:
                self.setTabIcon(getIcon('qta:mdi.chat-outline'))

            # System tray notification if the main window is not visible
            if not self.app.mainWindow.isActiveWindow():
                self.app.systemTrayMessage(
                    iChat(),
                    iChatMessageNotification(
                        self.channel,
                        message.peerCtx.spaceHandle.short
                    ),
                    timeout=3000
                )

            self.chatView.hChat.chatMsgReceived.emit(QVariant({
                'uid': message.uid,
                'time': now.strftime('%H:%M'),
                'local': fromUs,
                'spaceHandle': str(message.peerCtx.spaceHandle.short),
                'message': markitdown(message.messageBody),
                'avatarPath': avatarPath
            }))

            if len(message.links) > 0:
                attach = []
                for obj in message.links:
                    if not isinstance(obj, str):
                        continue
                    try:
                        path = IPFSPath(obj, autoCidConv=True)
                        if not path.valid:
                            continue

                        mType, stat = await self.app.rscAnalyzer(path)
                        if not mType or not stat:
                            continue

                        attach.append({
                            'objPath': path.objPath,
                            'url': path.ipfsUrl,
                            'mimeType': str(mType),
                            'stat': stat
                        })
                    except Exception:
                        continue

                if len(attach) > 0:
                    self.chatView.hChat.chatMsgAttachments.emit(
                        message.uid, QVariant(attach))

        elif message.command == ChatRoomMessage.COMMAND_JOIN:
            self.chatView.hChat.chatJoinLeftReceived.emit(QVariant({
                'avatarPath': avatarPath,
                'status': 'joined',
                'time': now.strftime('%H:%M'),
                'local': fromUs,
                'spaceHandle': str(message.peerCtx.spaceHandle.short)
            }))
            await self.userHeartbeat(message)
        elif message.command == ChatRoomMessage.COMMAND_LEAVE:
            self.chatView.hChat.chatJoinLeftReceived.emit(QVariant({
                'avatarPath': avatarPath,
                'status': 'left',
                'time': now.strftime('%H:%M'),
                'local': fromUs,
                'spaceHandle': str(message.peerCtx.spaceHandle.short)
            }))
            await self.userLeft(message)

    def onSendMessage(self):
        messageText = self.ui.message.text()
        if not messageText:
            return

        self.ui.message.clear()
        ensure(self.sendMessage(messageText))

    @ipfsOp
    async def sendMessage(self, ipfsop, msgText):
        links = []
        words = msgText.split()

        def addPath(path):
            oPath = str(path)
            if len(links) < 4 and oPath not in links:
                links.append(oPath)

        for word in words:
            path = IPFSPath(word, autoCidConv=True)
            if path.valid:
                addPath(path)

        matches = re.findall(r'"([^"]*)"', msgText)
        for match in matches:
            path = IPFSPath(match, autoCidConv=True)
            if path.valid:
                addPath(path)

        await self.psService.send(
            await ChatRoomMessage.make(
                self.psService.jwsTokenCid,
                command='MSGMARKDOWN',
                params=[msgText],
                links=links
            )
        )

    @ipfsOp
    async def sendStatusJoin(self, ipfsop):
        msg = await ChatRoomMessage.make(
            self.psService.jwsTokenCid,
            command='JOIN'
        )

        await self.psService.send(msg)

    async def startHeartbeatTask(self):
        self.hbTask = await self.app.scheduler.spawn(self.heartbeatTask())

    async def heartbeatTask(self):
        while True:
            await asyncio.sleep(60)
            await self.psService.send(
                await ChatRoomMessage.make(
                    self.psService.jwsTokenCid,
                    command=ChatRoomMessage.COMMAND_HEARTBEAT
                )
            )

    async def onClose(self):
        await self.hbTask.close()
        await self.psService.send(
            await ChatRoomMessage.make(
                self.psService.jwsTokenCid,
                command=ChatRoomMessage.COMMAND_LEAVE
            )
        )

        await self.chans.leaveChannel(self.channel, self.psService)
        return True
