from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import Qt

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.pubsub.messages import ChatRoomMessage
from galacteek.ipfs.pubsub import TOPIC_CHAT
from galacteek import ensure

from .helpers import questionBox
from .widgets import GalacteekTab

from . import ui_chatroom


class ChatRoomWidget(GalacteekTab):
    def __init__(self, gWindow):
        super(ChatRoomWidget, self).__init__(gWindow)

        self.chatWidget = QWidget()
        self.vLayout.addWidget(self.chatWidget)

        self.ui = ui_chatroom.Ui_Form()
        self.ui.setupUi(self.chatWidget)
        self.ui.chatLog.setOpenExternalLinks(False)
        self.ui.chatLog.setOpenLinks(False)
        self.ui.chatLog.anchorClicked.connect(self.onAnchorClicked)

        self.app.ipfsCtx.pubsub.chatRoomMessageReceived.connect(
            self.onChatMessageReceived)
        self.ui.sendButton.clicked.connect(self.onSendMessage)
        self.ui.message.returnPressed.connect(self.onSendMessage)
        self.ui.message.setFocusPolicy(Qt.StrongFocus)
        self.ui.chatLog.setFocusPolicy(Qt.NoFocus)

    def focusMessage(self):
        self.ui.message.setFocus(Qt.OtherFocusReason)

    def onAnchorClicked(self, url):
        path = IPFSPath(url.toString(), autoCidConv=True)
        if path.valid:
            if questionBox('Open link', 'Open <b>{}</b> ?'.format(str(path))):
                ensure(self.app.resourceOpener.open(path, openingFrom='chat'))

    def onChatMessageReceived(self, message):
        self.ui.chatLog.moveCursor(QTextCursor.End, QTextCursor.MoveAnchor)
        self.ui.chatLog.insertPlainText('\n')
        self.ui.chatLog.insertHtml('<br>')

        formatted = '<p>'
        formatted += '<span style="color: black">({date})</span> '.format(
            date=message.date)
        formatted += '<span style="color: #006080">#{channel}</span> '.format(
            channel=message.channel)
        formatted += '<span style="color: #e67300">{sender}</span>: '.format(
            sender=message.sender)
        formatted += ' {message}'.format(message=message.message)
        formatted += '</p>'

        if len(message.links) > 0:
            for obj in message.links:
                path = IPFSPath(obj, autoCidConv=True)
                if not path.valid:
                    continue
                formatted += '<p>Link '
                formatted += '<a href="{objhref}">{name}<a>'.format(
                    objhref=path.ipfsUrl, name=path.objPath)
                formatted += '</p>'

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
        profile = ipfsop.ctx.currentProfile

        links = []
        words = msgText.split()
        for word in words:
            path = IPFSPath(word, autoCidConv=True)
            if path.valid:
                links.append(str(path))

        msg = ChatRoomMessage.make(
            profile.userInfo.spaceHandle.short,
            ChatRoomMessage.CHANNEL_GENERAL,
            msgText,
            links=links)
        await ipfsop.ctx.pubsub.send(TOPIC_CHAT, msg)
