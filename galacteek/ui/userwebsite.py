from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QDialogButtonBox
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QSpacerItem
from PyQt5.QtWidgets import QSizePolicy

from PyQt5.QtCore import QRegExp
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import Qt

from PyQt5.QtGui import QRegExpValidator

from galacteek import ensure
from galacteek import partialEnsure
from galacteek.ipfs import ipfsOp

from .widgets import MarkdownInputWidget
from .widgets import GalacteekTab
from .helpers import runDialogAsync
from .helpers import getMimeIcon
from .helpers import getIcon
from .helpers import messageBox
from .helpers import questionBoxAsync

from .dialogs import IPTagsSelectDialog
from .i18n import iNewBlogPost


class UserWebsiteManager(QObject):
    postError = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.newBlogPostAction = QAction(
            getMimeIcon('text/html'),
            iNewBlogPost(), self,
            triggered=self.onNewPost
        )

        self.blogMenu = QMenu('Blog')
        self.blogMenu.setIcon(getIcon('blog.png'))
        self.blogMenu.addAction(self.newBlogPostAction)

        self.postError.connect(lambda err: messageBox(err))

    def onNewPost(self):
        ensure(runDialogAsync(WebsiteAddPostDialog, manager=self))


class WebsiteAddPostDialog(QDialog):
    def __init__(self, manager=None, parent=None):
        super().__init__(parent)

        self.manager = manager

        self.setWindowTitle(iNewBlogPost())
        self.app = QApplication.instance()
        self.contents = None

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)

        mainLayout = QVBoxLayout()

        self.title = QLineEdit()
        regexp = QRegExp(r"[\w_-\s@\'\",\.]+")
        self.title.setValidator(QRegExpValidator(regexp))
        self.title.setMaxLength(92)

        titleLayout = QHBoxLayout()
        titleLayout.addWidget(QLabel('Title'))
        titleLayout.addWidget(self.title)

        self.markdownInput = MarkdownInputWidget(self)
        mainLayout.addLayout(titleLayout)

        mainLayout.addWidget(QLabel(
            '''<p align="center">You can drag-and-drop IPFS files
                in the Markdown input editor</p>'''
        ))

        mainLayout.addWidget(self.markdownInput)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

        buttonBox.accepted.connect(partialEnsure(self.accept))
        buttonBox.rejected.connect(self.reject)

        self.title.setFocus(Qt.OtherFocusReason)

    async def accept(self):
        self.contents = self.markdownInput.markdownText()
        title = self.title.text()

        if len(title) == 0 or len(self.contents) == 0:
            return messageBox('Please provide a title and post body')

        self.setEnabled(False)
        tagsDialog = await runDialogAsync(IPTagsSelectDialog)

        await self.blogPost(title, self.contents, tagsDialog.destTags)

    @ipfsOp
    async def blogPost(self, ipfsop, title, body, tags):
        profile = ipfsop.ctx.currentProfile

        try:
            await profile.userWebsite.blogPost(
                title, body, tags=tags)
        except Exception as err:
            messageBox(str(err))
            self.setEnabled(True)
        else:
            self.done(1)


class WebsiteAddPostTab(GalacteekTab):
    def __init__(self, gWindow):
        super().__init__(gWindow)

        self.app = QApplication.instance()

        self.posting = 0

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)

        self.title = QLineEdit()
        self.title.setMaximumWidth(600)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.textEdited.connect(self.onTitleEdited)

        regexp = QRegExp(r"[\w_-\s]+")
        self.title.setValidator(QRegExpValidator(regexp))
        self.title.setMaxLength(92)

        titleLayout = QHBoxLayout()
        titleLayout.setSpacing(64)
        titleLayout.addItem(
            QSpacerItem(100, 10, QSizePolicy.Minimum, QSizePolicy.Minimum))
        titleLayout.addWidget(QLabel('Title'))
        titleLayout.addWidget(self.title)
        titleLayout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.markdownInput = MarkdownInputWidget()

        self.vLayout.setContentsMargins(20, 20, 20, 20)
        self.vLayout.addLayout(titleLayout)

        self.vLayout.addWidget(self.markdownInput)
        self.vLayout.addWidget(buttonBox, 0, Qt.AlignCenter)

        buttonBox.accepted.connect(partialEnsure(self.process))
        buttonBox.rejected.connect(partialEnsure(self.postCancelled))

        self.title.setFocus(Qt.OtherFocusReason)

    def onTitleEdited(self, text):
        self.setTabName(text if text else iNewBlogPost())

    async def process(self):
        contents = self.markdownInput.markdownText()
        title = self.title.text()

        if len(title) == 0 or len(contents) == 0:
            return messageBox('Please provide a title and post body')

        self.setEnabled(False)
        tagsDialog = await runDialogAsync(IPTagsSelectDialog)

        await self.blogPost(title, contents, tagsDialog.destTags)

    @ipfsOp
    async def blogPost(self, ipfsop, title, body, tags):
        profile = ipfsop.ctx.currentProfile

        try:
            self.posting = 1
            await profile.userWebsite.blogPost(
                title, body, tags=tags)
        except Exception as err:
            self.posting = 0
            messageBox(str(err))
            self.setEnabled(True)
        else:
            self.posting = 2
            self.tabRemove()

    async def onClose(self):
        contents = self.markdownInput.markdownText()

        if self.posting == 1:
            return False

        elif self.posting == 0 and len(contents) > 0:
            return await self.cancelCheck()

        return True

    async def cancelCheck(self):
        return await questionBoxAsync(
            'Blog post',
            'Cancel ?')

    async def postCancelled(self):
        self.tabRemove()
