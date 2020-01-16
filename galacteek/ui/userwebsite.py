from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QDialogButtonBox
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QLineEdit

from PyQt5.QtCore import QRegExp
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import Qt

from PyQt5.QtGui import QRegExpValidator

from galacteek import ensure
from galacteek.ipfs import ipfsOp

from .widgets import MarkdownInputWidget
from .helpers import runDialog
from .helpers import getMimeIcon
from .helpers import getIcon
from .helpers import messageBox


def iNewBlogPost():
    return QCoreApplication.translate('GalacteekWindow', 'New blog post')


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
        runDialog(WebsiteAddPostDialog, manager=self)


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
        regexp = QRegExp(r"[A-Za-z0-9_-\s\']+")
        self.title.setValidator(QRegExpValidator(regexp))

        titleLayout = QHBoxLayout()
        titleLayout.addWidget(QLabel('Title'))
        titleLayout.addWidget(self.title)

        self.markdownInput = MarkdownInputWidget(self)
        mainLayout.addLayout(titleLayout)
        mainLayout.addWidget(self.markdownInput)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        self.title.setFocus(Qt.OtherFocusReason)

    def accept(self):
        self.contents = self.markdownInput.markdownText()
        title = self.title.text()

        if len(title) == 0 or len(self.contents) == 0:
            return messageBox('Please provide a title and post body')

        self.setEnabled(False)
        ensure(self.blogPost(title, self.contents))

    @ipfsOp
    async def blogPost(self, ipfsop, title, body):
        profile = ipfsop.ctx.currentProfile

        try:
            await profile.userWebsite.blogPost(title, body)
        except Exception as err:
            messageBox(str(err))
            self.setEnabled(True)
        else:
            self.done(1)
