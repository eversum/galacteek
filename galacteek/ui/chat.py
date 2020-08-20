import asyncio
import functools
import time
import weakref

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QToolButton

from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QSortFilterProxyModel
from PyQt5.QtCore import QRegExp

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtGui import QStandardItem

from PyQt5.QtWidgets import QAbstractItemView

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.pubsub.messages.chat import ChatRoomMessage
from galacteek.ipfs.pubsub.service import chatChannelTopic
from galacteek.ipfs.pubsub.service import PSChatChannelService
from galacteek.core.ps import makeKeyChatChannel
from galacteek.core.ps import psSubscriber
from galacteek.core import SingletonDecorator
from galacteek.dweb.markdown import markitdown

from galacteek.core import datetimeNow
from galacteek import ensure
from galacteek import ensureLater
from galacteek import log
from galacteek import partialEnsure
from galacteek.core.modelhelpers import UneditableStringListModel

from .dwebspace import WS_PEERS
from .helpers import getIcon
from .helpers import inputTextCustom
from .helpers import questionBoxAsync
from .helpers import messageBox
from .helpers import runDialogAsync
from .widgets import GalacteekTab
from .widgets import PopupToolButton
from .i18n import iChat
from .i18n import iChatMessageNotification

from . import ui_chatchannelslist
from . import ui_chatchannelnew
from . import ui_chatroom


@SingletonDecorator
class ChatChannels(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.channelWidgets = {}

    @ipfsOp
    async def createChannel(self, ipfsop, channel):
        dagChannels = ipfsop.ctx.currentProfile.dagChatChannels
        dagChannels.register(channel)

    @ipfsOp
    async def joinChannel(self, ipfsop, channel):
        topic = chatChannelTopic(channel)
        service = ipfsop.ctx.pubsub.byTopic(topic)

        if not service:
            key = makeKeyChatChannel(channel)
            service = PSChatChannelService(
                ipfsop.ctx,
                self.app.ipfsClient,
                channel,
                key,
                scheduler=self.app.scheduler
            )
            ipfsop.ctx.pubsub.reg(service)
            await service.start()

        w = self.channelWidgets.get(channel)
        if not w:
            self.channelWidgets[channel] = w = ChatRoomWidget(
                channel, service, self.app.mainWindow)

        ensure(w.startHeartbeatTask())
        ensureLater(1, w.sendStatusJoin)

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

        self.channelsModel = UneditableStringListModel(self)
        self.channelsProxyModel = QSortFilterProxyModel(self)
        self.channelsProxyModel.setSourceModel(self.channelsModel)
        self.ui.channelsView.setModel(self.channelsProxyModel)
        self.ui.channelsView.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.ui.searchLine.textChanged.connect(self.onApplySearch)

    @ipfsOp
    async def initDialog(self, ipfsop):
        dagChannels = ipfsop.ctx.currentProfile.dagChatChannels
        self.channelsModel.setStringList(dagChannels.channels)

    def onApplySearch(self):
        self.channelsProxyModel.setFilterRegExp(self.ui.searchLine.text())

    def onJoinClicked(self):
        idx = self.ui.channelsView.currentIndex()
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


class ChatChannelNewDialog(QDialog):
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

        ensure(self.chans.createChannel(channel))
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
            'Create channel',
            self.onCreateChannel
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
        ensure(runDialogAsync(ChatChannelNewDialog))

    def old(self):
        channel = inputTextCustom(label='Channel name')
        if channel:
            ensure(self.chans.createChannel(channel))


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


class ChatRoomWidget(GalacteekTab):
    def __init__(self, channel, psService, gWindow):
        super(ChatRoomWidget, self).__init__(gWindow)

        self.lock = asyncio.Lock()

        self.participantsModel = ParticipantsModel(self)
        self.participantsModel.setHorizontalHeaderLabels(
            ['SpaceHandle', 'HB']
        )

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
        self.ui.chatLog.setOpenExternalLinks(False)
        self.ui.chatLog.setOpenLinks(False)
        self.ui.chatLog.anchorClicked.connect(
            partialEnsure(self.onAnchorClicked))

        self.ui.sendButton.clicked.connect(self.onSendMessage)
        self.ui.message.returnPressed.connect(self.onSendMessage)
        self.ui.message.setFocusPolicy(Qt.StrongFocus)
        self.ui.chatLog.setFocusPolicy(Qt.NoFocus)

        self.ui.usersView.setModel(self.participantsModel)
        self.ui.usersView.hideColumn(0)

    def focusMessage(self):
        self.ui.message.setFocus(Qt.OtherFocusReason)

    async def onAnchorClicked(self, url):
        path = IPFSPath(url.toString(), autoCidConv=True)
        if path.valid:
            if await questionBoxAsync(
                    'Open link', 'Open <b>{}</b> ?'.format(str(path))):
                ensure(self.app.resourceOpener.open(path, openingFrom='chat'))

    async def onTabChanged(self):
        self.setTabIcon(getIcon('qta:mdi.chat-outline'))

    async def participantsHandles(self):
        return [p['handle'] for p in await self.participantsData()]

    async def participantsData(self):
        data = []
        async with self.lock:
            for row in range(self.participantsModel.rowCount()):
                data.append({
                    'handle': self.participantsModel.pData(row, 1),
                    'hbts': self.participantsModel.pData(row, 0),
                    'row': row
                })
        return data

    async def userHeartbeat(self, message):
        participants = await self.participantsHandles()
        sHandleShort = message.peerCtx.spaceHandle.short

        async with self.lock:
            if sHandleShort not in participants:
                itemHandle = ParticipantItem(sHandleShort)
                itemHandle.peerCtx = weakref.ref(message.peerCtx)
                itemTs = QStandardItem(str(time.time()))

                self.participantsModel.invisibleRootItem().appendRow(
                    [itemTs, itemHandle]
                )

    async def userLeft(self, message):
        await self.removeUser(message.peerCtx.spaceHandle.short)

    async def removeUser(self, handle):
        data = await self.participantsData()

        async with self.lock:
            for p in data:
                if p['handle'] == handle:
                    self.participantsModel.removeRow(p['row'])

    async def removeInactiveUsers(self):
        now = time.time()
        data = await self.participantsData()

        async with self.lock:
            for p in data:
                try:
                    if (now - float(p['hbts'])) > 60 * 3:
                        self.participantsModel.removeRow(p['row'])
                except Exception:
                    continue

    async def onChatMessageReceived(self, key, message):
        now = datetimeNow()

        if message.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_HEARTBEAT:
            await self.userHeartbeat(message)
            return

        self.ui.chatLog.moveCursor(QTextCursor.End, QTextCursor.MoveAnchor)
        self.ui.chatLog.insertPlainText('\n')

        formatted = '<p style="margin-left: 0px">'
        formatted += '<span style="color: black">{date}</span> '.format(
            date=now.strftime('%H:%M'))
        formatted += '<span style="color: #e67300">{sender}</span>: '.format(
            sender=message.peerCtx.spaceHandle.short)

        if message.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_MESSAGE:
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
                    timeout=4000
                )

            formatted += '<p> {message}</p>'.format(
                message=markitdown(message.message))
        elif message.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_JOINED:
            await self.userHeartbeat(message)
            formatted += '<span style="color: blue">{message}</span>'.format(
                message='joined the channel')
            formatted += '</p>'
        elif message.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_LEFT:
            await self.userLeft(message)
            formatted += '<span style="color: red">{message}</span>'.format(
                message='left the channel')
            formatted += '</p>'
        elif message.chatMessageType == ChatRoomMessage.CHATMSG_TYPE_HEARTBEAT:
            pass

        if len(message.links) > 0:
            for obj in message.links:
                if not isinstance(obj, str):
                    continue
                try:
                    path = IPFSPath(obj, autoCidConv=True)
                    if not path.valid:
                        continue
                    formatted += '<p style="margin-left: 30px">Link '
                    formatted += '<a href="{objhref}">{name}<a>'.format(
                        objhref=path.ipfsUrl, name=path.objPath)
                    formatted += '</p>'
                except Exception:
                    continue

        self.ui.chatLog.insertHtml('<br>')
        self.ui.chatLog.insertHtml(formatted)

        self.ui.chatLog.verticalScrollBar().setValue(
            self.ui.chatLog.verticalScrollBar().maximum())

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

        for word in words:
            path = IPFSPath(word, autoCidConv=True)
            if path.valid:
                links.append(str(path))

        await self.psService.send(
            await ChatRoomMessage.make(
                msgText,
                links=links)
        )

    @ipfsOp
    async def sendStatusJoin(self, ipfsop):
        msg = await ChatRoomMessage.make(
            type=ChatRoomMessage.CHATMSG_TYPE_JOINED
        )

        await self.psService.send(msg)

    async def startHeartbeatTask(self):
        self.hbTask = await self.app.scheduler.spawn(self.heartbeatTask())

    async def heartbeatTask(self):
        while True:
            await asyncio.sleep(15)
            await self.psService.send(
                await ChatRoomMessage.make(
                    type=ChatRoomMessage.CHATMSG_TYPE_HEARTBEAT
                )
            )

            await self.removeInactiveUsers()

    async def onClose(self):
        await self.hbTask.close()
        await self.psService.send(
            await ChatRoomMessage.make(
                type=ChatRoomMessage.CHATMSG_TYPE_LEFT
            )
        )

        return True
