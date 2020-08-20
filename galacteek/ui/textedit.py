import functools
import aiofiles
import os.path
import os
import uuid
import re
import shutil
import difflib
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QScrollArea
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtWidgets import QPlainTextEdit
from PyQt5.QtWidgets import QPlainTextDocumentLayout
from PyQt5.QtWidgets import QSpacerItem
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QFrame
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QFileSystemModel
from PyQt5.QtWidgets import QTreeView
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QTextBrowser
from PyQt5.QtWidgets import QDialog

from PyQt5.QtCore import QFileInfo
from PyQt5.QtCore import QDateTime
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QRegularExpression
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QDir
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import QModelIndex
from PyQt5.QtCore import QItemSelectionModel

from PyQt5.QtGui import QMouseEvent
from PyQt5.QtGui import QTextDocument
from PyQt5.QtGui import QTextFormat
from PyQt5.QtGui import QTextCursor
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QSyntaxHighlighter
from PyQt5.QtGui import QTextCharFormat
from PyQt5.QtGui import QFont
from PyQt5.QtGui import QKeySequence

import qtawesome as qta

from galacteek import log
from galacteek import partialEnsure
from galacteek.ipfs.ipfsops import *
from galacteek.core import isoformat
from galacteek.core.asynclib import asyncReadTextFileChunked
from galacteek.core.asynclib import threadExec
from galacteek.appsettings import *
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.mimetype import detectMimeType
from galacteek.ipfs.mimetype import detectMimeTypeFromFile
from galacteek.ipfs.mimetype import detectMimeTypeFromBuffer
from galacteek.dweb.markdown import markitdown

from .helpers import *

from .widgets import IPFSWebView
from .widgets import AnimatedLabel
from .widgets import IPFSPathClipboardButton
from .widgets import IPFSUrlLabel
from .widgets import GalacteekTab
from .widgets import CheckableToolButton
from .widgets import HashmarkThisButton
from .widgets import MarkdownTextEdit
from .clips import RotatingCubeRedFlash140d
from .i18n import *


def iSave():
    return QCoreApplication.translate('textEditor',
                                      'Save')


def iAddNewFile():
    return QCoreApplication.translate('textEditor',
                                      'Create new file')


def iImportFile():
    return QCoreApplication.translate('textEditor',
                                      'Import file')


def iImportError():
    return QCoreApplication.translate('textEditor',
                                      'Import error')


def iImportDir():
    return QCoreApplication.translate('textEditor',
                                      'Import directory')


def iAddNewDir():
    return QCoreApplication.translate('textEditor',
                                      'Create new directory')


def iEdit():
    return QCoreApplication.translate('textEditor',
                                      'Edit')


def iFilesystemView():
    return QCoreApplication.translate('textEditor',
                                      'Filesystem view')


def iEditorView():
    return QCoreApplication.translate('textEditor',
                                      'Editor view')


def iPreview():
    return QCoreApplication.translate('textEditor',
                                      'Preview')


def iObjectDiff():
    return QCoreApplication.translate('textEditor',
                                      'Object diff')


def iAutoMarkdownToHtmlSave():
    return QCoreApplication.translate(
        'textEditor',
        'Automatic markdown to HTML saving'
    )


def iOfflineMode():
    return QCoreApplication.translate(
        'textEditor',
        'Offline mode (announce your content manually later)')


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """
    An horrendous Python syntax highligher
    """

    def __init__(self, doc):
        super().__init__(doc)

        self.fmt1 = self.charFormat(color=Qt.red)
        self.fmt2 = self.charFormat(color=Qt.blue)
        self.fmt3 = self.charFormat(color=QColor('#AA1811'))
        self.fmt4 = self.charFormat(color=QColor('#6C0404'))
        self.fmt5 = self.charFormat(color=QColor('#65416C'))

        self.exprs = [
            (r'^(?<instr>from)\s', self.fmt1),
            (r'\s*(?<instr>import)\s', self.fmt1),
            (r'(?<instr>def) ', self.fmt3),
            (r'(?<instr>\s*(async|await|print|return|yield|pass|raise)) ',
                self.fmt3),
            (r'(?<instr>\s*(True|False|None))\s', self.fmt5),
            (r'^(?<instr>class)\s', self.fmt4),
            (r"(?<instr>('[a-zA-Z0-9_-]*'))", self.fmt4),
            (r"(?<instr>(\"[a-zA-Z0-9_-]*\"))", self.fmt4),
            (r"^((?<instr>(\s+)(if|elif|else|or|not|is)\s)", self.fmt4),
            (r"^((?<instr>(\s+)(try|except))\s", self.fmt4),
            (r"^(?<instr>(\s*)#.*$)", self.fmt5),
        ]

    def charFormat(self, color=Qt.red, fontWeight=QFont.Bold):
        fmt = QTextCharFormat()
        fmt.setFontWeight(fontWeight)
        fmt.setForeground(color)
        return fmt

    def highlightBlock(self, text):
        for expr in self.exprs:
            fmt = expr[1]
            rExpr = QRegularExpression(expr[0])

            if not rExpr.isValid():
                continue

            matches = rExpr.globalMatch(text)

            if not matches.isValid():
                continue

            while matches.hasNext():
                match = matches.next()
                instr = match.captured('instr')
                if instr:
                    self.setFormat(
                        match.capturedStart(), match.capturedLength(), fmt)


defaultStyleSheet = '''
    QPlainTextEdit {
        padding: 5px;
        color: #242424;
        background-color: #F0F7F7;
        font: 14pt "Courier";
    }
'''


class EditorLegacy(QTextEdit):
    def __init__(self, parent, lineWrap=80, tabReplace=False):
        super(Editor, self).__init__(parent)

        self.setLineWrapMode(QTextEdit.FixedColumnWidth)
        self.setLineWrapColumnOrWidth(lineWrap)
        self.setStyleSheet(defaultStyleSheet)
        self.tabReplace = tabReplace

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab and self.tabReplace:
            self.insertPlainText(' ' * 4)
        else:
            super().keyPressEvent(event)

    def connectSignals(self):
        disconnectSig(self.cursorPositionChanged, self.highlightCurrentLine)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

    def highlightCurrentLine(self):
        extraSelections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor('#e2dd8e')

            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)

        self.setExtraSelections(extraSelections)


def filenameIsMarkdown(filename):
    return os.path.splitext(filename)[1] in [
        '.md',
        '.mdown',
        '.mkd',
        '.mkdn',
        '.markdown',
        '.mdwn'
    ]


def filenameIsHtml(filename):
    return os.path.splitext(filename)[1] in [
        '.html',
        '.htm',
    ]


class Editor(MarkdownTextEdit):
    def __init__(self, parent, lineWrap=80, tabReplace=False):
        super(Editor, self).__init__(parent)

        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setStyleSheet(defaultStyleSheet)
        self.tabReplace = tabReplace

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab and self.tabReplace:
            self.insertPlainText(' ' * 4)
        else:
            super().keyPressEvent(event)

    def connectSignals(self):
        disconnectSig(self.cursorPositionChanged, self.highlightCurrentLine)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

    def highlightCurrentLine(self):
        extraSelections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor('#e2dd8e')

            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)

        self.setExtraSelections(extraSelections)


class EditHistory(QScrollArea):
    def __init__(self, widgetHeight=60, parent=None):
        super(EditHistory, self).__init__(parent)

        self.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setWidgetResizable(True)
        self.setMaximumHeight(widgetHeight)

        self.frame = QFrame(self)
        self.frame.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.fLayout = QVBoxLayout()
        self.frame.setLayout(self.fLayout)
        self.setWidget(self.frame)


class Document(QTextDocument):
    modified = pyqtSignal()
    filenameChanged = pyqtSignal(str)

    def __init__(self, encoding=None, name=None, text='', parent=None,
                 textLayout=True):
        super().__init__(text, parent)

        if textLayout is True:
            self.setDocumentLayout(QPlainTextDocumentLayout(self))

        self._filename = name
        self._changed = False
        self._encoding = encoding if encoding else 'utf-8'
        self._previewDocument = None
        self.setDefaultStyleSheet(defaultStyleSheet)
        self.setModified(False)
        self.modificationChanged.connect(self.onModifChange)

    @property
    def previewDocument(self):
        return self._previewDocument

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, name):
        self._filename = name
        self.filenameChanged.emit(name)

    @property
    def changed(self):
        return self._changed

    @property
    def encoding(self):
        return self._encoding

    def onModifChange(self, changed):
        if self.changed is False and changed is True:
            self.modified.emit()

        self._changed = changed


class TextEditorTab(GalacteekTab):
    def __init__(self, editing=False, pyramidOrigin=None, parent=None):
        super(TextEditorTab, self).__init__(parent)

        self.editor = TextEditorWidget(
            editing=editing,
            pyramidOrigin=pyramidOrigin,
            parent=self
        )
        self.editor.documentChanged.connect(self.onDocChange)
        self.editor.documentNameChanged.connect(self.onDocnameChanged)

        self.vLayout.addWidget(self.editor)

    def onDocChange(self, doc):
        self.changeTabName(doc.filename)

    def changeTabName(self, name):
        if name is None:
            self.setTabName(iUnknown(), widget=self)

        elif len(name) > 16:
            cutoff = int(max(
                4 * (len(name) / 5),
                len(name) / 2
            ))

            self.setTabName(
                '... {0}'.format(name[cutoff:]),
                widget=self
            )
        else:
            self.setTabName(name, widget=self)

    def onDocnameChanged(self, doc, name):
        if doc is self.editor.currentDocument:
            self.changeTabName(doc.filename)

    async def onClose(self):
        if await self.editor.checkChanges() is True:
            if self.editor.localCheckoutChanged is True:
                unsaved = await questionBoxAsync(
                    'Unsaved changes',
                    'This session has unsynced content, continue ?')
                if unsaved is False:
                    return unsaved

            self.editor.cleanup()
            return True
        return False


class CheckoutTreeView(QTreeView):
    doubleClick = pyqtSignal(QModelIndex, QFileInfo)
    itemRightClick = pyqtSignal(QModelIndex, QMouseEvent, QFileInfo)

    def mouseDoubleClickEvent(self, event):
        idx = self.currentIndex()
        fInfo = self.model().fileInfo(idx)

        if fInfo:
            path = Path(fInfo.absoluteFilePath())
            if path.is_dir():
                super(CheckoutTreeView, self).mouseDoubleClickEvent(event)
            elif path.is_file():
                self.doubleClick.emit(idx, fInfo)

    def mousePressEvent(self, event):
        item = self.indexAt(event.pos())

        if item.isValid():
            super(CheckoutTreeView, self).mousePressEvent(event)
        else:
            self.clearSelection()

            self.selectionModel().setCurrentIndex(
                QModelIndex(),
                QItemSelectionModel.Select
            )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            idx = self.currentIndex()
            fInfo = self.model().fileInfo(idx)

            if fInfo:
                self.itemRightClick.emit(idx, event, fInfo)
        else:
            super(CheckoutTreeView, self).mouseReleaseEvent(event)


class PreviewWidget(IPFSWebView):
    pass


class TextEditorWidget(QWidget):
    """
    Simple Editor widget that stores the edited files in a unixfs node
    """

    rootMultihashChanged = pyqtSignal(str)
    documentChanged = pyqtSignal(Document)
    documentNameChanged = pyqtSignal(Document, str)
    filenameEntered = pyqtSignal(str)

    def __init__(self, offline=False, editing=False, sessionDagCid=None,
                 pyramidOrigin=None,
                 pyramidAutoPush=False, parent=None):
        super(TextEditorWidget, self).__init__(parent)

        self.app = QApplication.instance()
        self.setLayout(QVBoxLayout(self))
        self.textEditor = Editor(self)

        self.checkoutPath = None
        self.pyramidOrigin = pyramidOrigin
        self.pyramidAutoPush = pyramidAutoPush

        self.busyCube = AnimatedLabel(
            RotatingCubeRedFlash140d(speed=100),
            parent=self
        )
        self.busyCube.clip.setScaledSize(QSize(24, 24))
        self.busyCube.startClip()
        self.busyCube.hide()

        self._previewTimer = QTimer(self)
        self._previewTimer.timeout.connect(self.onPreviewRerender)
        self._editing = editing
        self._currentDocument = None
        self._localCheckoutChanged = False
        self._unixDir = None

        self.model = QFileSystemModel()

        self.filesView = CheckoutTreeView(self)
        self.filesView.setModel(self.model)
        self.filesView.doubleClick.connect(self.onFsViewItemDoubleClicked)
        self.filesView.itemRightClick.connect(self.onFsViewRightClicked)

        self.model.setFilter(
            QDir.Files | QDir.AllDirs | QDir.NoDot | QDir.NoDotDot
        )
        self.model.setRootPath(self.checkoutPath)

        self.filesView.setVisible(False)
        self.filesView.hideColumn(1)
        self.filesView.hideColumn(2)
        self.filesView.hideColumn(3)

        self.setObjectName('textEditor')
        self.inPreview = False
        self.offline = offline

        self.editHistory = EditHistory(parent=self)
        self.editHistory.hide()
        self.copiesLayout = self.editHistory.fLayout

        self.ctrlLayout = QHBoxLayout()

        self.editorViewButton = CheckableToolButton(
            icon=qta.icon('fa.edit'),
            toggled=self.onEditorViewToggled, parent=self
        )

        self.editorViewButton.setToolTip(iEditorView())

        self.offlineModeButton = CheckableToolButton(
            icon=getIcon('offline.png')
        )
        self.offlineModeButton.setChecked(offline)
        self.offlineModeButton.setEnabled(False)
        self.offlineModeButton.setVisible(False)
        self.offlineModeButton.setToolTip(iOfflineMode())

        self.autoMdHtmlSaveButton = CheckableToolButton(
            icon=qta.icon('fa5b.markdown')
        )
        self.autoMdHtmlSaveButton.setToolTip(iAutoMarkdownToHtmlSave())
        self.autoMdHtmlSaveButton.hide()

        self.previewButton = CheckableToolButton(
            icon=getIcon('document-preview.png'),
            toggled=self.onPreviewToggled, parent=self
        )
        self.previewButton.setToolTip(iPreview())

        self.editorViewButton.setChecked(True)

        self.fsViewButton = CheckableToolButton(
            icon=getIcon('folder-open.png'),
            toggled=self.onFsViewToggled, parent=self
        )
        self.fsViewButton.setEnabled(True)
        self.fsViewButton.setChecked(False)
        self.fsViewButton.setToolTip(iFilesystemView())

        self.editButton = CheckableToolButton(
            toggled=self.onEditToggled, parent=self
        )

        self.saveButton = QToolButton(self)
        self.saveButton.setIcon(getIcon('save-file.png'))
        self.saveButton.clicked.connect(self.onSave)
        self.saveButton.setToolTip(iSave())
        self.saveButton.setEnabled(False)
        self.saveButton.setShortcut(QKeySequence('Ctrl+s'))

        self.strokeIcon = getIcon('stroke-cube.png')

        self.editButton.setText(iEdit())

        self.unixDirCid = None
        self.unixDirPath = None
        self.unixDirDescrLabel = QLabel('Current session:')
        self.unixDirLabel = IPFSUrlLabel(
            None, invalidPathLabel='No session yet')
        self.unixDirClipButton = IPFSPathClipboardButton(None, parent=self)

        self.nameInputLabel = QLabel('File name')
        self.nameInputLine = QLineEdit('', self)
        self.nameInputLine.setMaximumWidth(160)
        self.nameInputValidate = QPushButton('OK')
        self.nameInputValidate.setMaximumWidth(40)
        self.nameInputValidate.clicked.connect(self.onNameInput)
        self.nameInputLine.returnPressed.connect(self.onNameInput)

        self.filenameEntered.connect(self.onFilenameEntered)

        self.ctrlLayout.addWidget(self.busyCube)
        self.ctrlLayout.addWidget(self.editButton)
        self.ctrlLayout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Minimum))
        self.ctrlLayout.addWidget(self.editorViewButton)
        self.ctrlLayout.addWidget(self.previewButton)
        self.ctrlLayout.addWidget(self.fsViewButton)
        self.ctrlLayout.addWidget(self.offlineModeButton)
        self.ctrlLayout.addWidget(self.autoMdHtmlSaveButton)
        self.ctrlLayout.addWidget(self.saveButton)

        self.ctrlLayout.addWidget(self.nameInputLabel)
        self.ctrlLayout.addWidget(self.nameInputLine)
        self.ctrlLayout.addWidget(self.nameInputValidate)

        self.showNameInput(False)

        self.ctrlLayout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.ctrlLayout.addWidget(self.unixDirDescrLabel)
        self.ctrlLayout.addWidget(self.unixDirLabel)
        self.ctrlLayout.addWidget(self.unixDirClipButton)

        self.textVLayout = QVBoxLayout()
        self.textHLayout = QHBoxLayout()
        self.textVLayout.addLayout(self.textHLayout)

        self.previewWidget = PreviewWidget(parent=self)
        self.previewWidget.hide()

        self.currentDocument = self.newDocument()
        self.textHLayout.addWidget(self.filesView)
        self.textHLayout.addWidget(self.textEditor)
        self.textHLayout.addWidget(self.previewWidget)

        optionsLayout = QHBoxLayout()
        self.tabReplaceButton = QCheckBox('Replace tabs', self)
        self.tabReplaceButton.stateChanged.connect(self.onTabReplaceToggled)
        self.tabReplaceButton.setEnabled(False)
        optionsLayout.addWidget(self.tabReplaceButton)
        self.textVLayout.addLayout(optionsLayout)

        self.layout().addLayout(self.ctrlLayout)
        self.layout().addWidget(self.editHistory)
        self.layout().addLayout(self.textVLayout)

        self.editing = editing
        self.rootMultihashChanged.connect(self.onSessionCidChanged)

        self.filesView.setMinimumWidth(self.width() / 4)

        self.textEditor.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.filesView.setSizePolicy(
            QSizePolicy.Minimum, QSizePolicy.Expanding)

    @property
    def unixDirCid(self):
        return self._unixDirCid

    @property
    def unixDir(self):
        return self._unixDir

    @unixDirCid.setter
    def unixDirCid(self, cid):
        self._unixDirCid = cid

    @property
    def editing(self):
        return self._editing

    @editing.setter
    def editing(self, editing):
        if not isinstance(editing, bool):
            return

        self._editing = editing
        self.textEditor.setReadOnly(not self.editing)
        self.editButton.setChecked(self.editing)
        self.tabReplaceButton.setEnabled(self.editing)
        self.applyStylesheet()

        if self.editing is True and self.checkoutPath is None:
            self.sessionNew()

    @property
    def localCheckoutChanged(self):
        return self._localCheckoutChanged

    @localCheckoutChanged.setter
    def localCheckoutChanged(self, val):
        self._localCheckoutChanged = val
        self.saveButton.setEnabled(val)

    @property
    def currentDocument(self):
        return self._currentDocument

    @currentDocument.setter
    def currentDocument(self, doc):
        self._currentDocument = doc
        self.textEditor.setDocument(self.currentDocument)

        self.applyOptionsForDocument()

        self.documentChanged.emit(self.currentDocument)
        self.currentDocument.setModified(False)

        self.currentDocument.modified.connect(
            functools.partial(self.saveButton.setEnabled, True))
        self.currentDocument.contentsChanged.connect(self.onDocumentChanged)

        self.applyStylesheet()

    def applyOptionsForDocument(self):
        if self.currentDocument.filename:
            if self.currentDocument.filename.endswith('.py'):
                self.highlighter = PythonSyntaxHighlighter(
                    self.currentDocument)
                self.tabReplaceButton.setChecked(True)
            if filenameIsMarkdown(self.currentDocument.filename):
                self.previewButton.setChecked(True)
                self.autoMdHtmlSaveButton.show()
            if filenameIsHtml(self.currentDocument.filename):
                self.previewButton.setChecked(True)
        else:
            self.highlighter = None

    def cleanup(self):
        if os.path.isdir(self.checkoutPath):
            log.debug('Cleaning up checkout directory: {}'.format(
                self.checkoutPath))
            shutil.rmtree(self.checkoutPath)

    def busy(self, busy=True):
        self.busyCube.setVisible(busy)
        self.setEnabled(not busy)

        if busy:
            self.busyCube.startClip()
        else:
            self.busyCube.stopClip()

    def onFsViewRightClicked(self, idx, event, fInfo):
        pos = event.globalPos()
        fullPath = fInfo.absoluteFilePath()
        _path = Path(fullPath)

        menu = QMenu(self)

        if not _path.exists() or _path.is_dir():
            menu.addAction(
                self.strokeIcon,
                iAddNewFile(), functools.partial(
                    self.fsAddFile, fullPath))
            menu.addSeparator()
            menu.addAction(
                self.strokeIcon,
                iAddNewDir(), functools.partial(
                    self.fsAddDirectory, fullPath))
            menu.addSeparator()

            menu.addAction(
                self.strokeIcon,
                iImportFile(), functools.partial(
                    self.fsImportFile, fullPath))
            menu.addSeparator()
            menu.addAction(
                self.strokeIcon,
                iImportDir(), functools.partial(
                    self.fsImportDirectory, fullPath))
            menu.addSeparator()

        menu.addAction(
            getIcon('clear-all.png'),
            'Delete',
            partialEnsure(self.fsDelete, fullPath)
        )

        menu.exec_(pos)

    async def fsDelete(self, path):
        if path and await questionBoxAsync(iRemove(), iRemoveFileAsk()):
            await self._fsDelete(path)

    def fsAddFile(self, root):
        if not root:
            rootDir = Path(self.checkoutPath)
        else:
            rootDir = Path(root)

        if not rootDir.is_dir():
            return

        name = self.nameInput()
        if name:
            filepath = rootDir.joinpath(name)
            if filepath.exists():
                return messageBox('Already exists')

            filepath.touch()
            self.localCheckoutChanged = True
            self.sessionViewUpdate()

    def fsImportFile(self, root):
        if not root:
            rootDir = Path(self.checkoutPath)
        else:
            rootDir = Path(root)

        filepath = fileSelect()

        if filepath:
            ensure(self._fsImportFile(filepath, str(rootDir)))

    async def _fsDelete(self, filepath):
        self.busy()

        try:
            if os.path.isdir(filepath):
                await self.app.loop.run_in_executor(
                    self.app.executor,
                    shutil.rmtree,
                    filepath
                )
            elif os.path.isfile(filepath):
                os.unlink(filepath)
        except Exception:
            pass

        self.localCheckoutChanged = True
        self.busy(False)

    async def _fsImportFile(self, filepath, rootDir):
        self.busy()

        try:
            await self.app.loop.run_in_executor(
                self.app.executor,
                shutil.copy,
                filepath,
                rootDir
            )
        except Exception:
            messageBox(iImportError())

        self.localCheckoutChanged = True
        self.busy(False)

    async def _fsImportDirectory(self, dirpath, dstDir):
        self.busy()

        try:
            await self.app.loop.run_in_executor(
                self.app.executor,
                shutil.copytree,
                dirpath,
                dstDir
            )
        except Exception:
            messageBox(iImportError())

        self.localCheckoutChanged = True
        self.busy(False)

    def fsImportDirectory(self, root):
        if not root:
            rootDir = Path(self.checkoutPath)
        else:
            rootDir = Path(root)

        dirpath = directorySelect()

        if dirpath:
            dstPath = rootDir.joinpath(os.path.basename(dirpath))
            ensure(self._fsImportDirectory(dirpath, str(dstPath)))

    def fsAddDirectory(self, root):
        if not root:
            rootDir = Path(self.checkoutPath)
        else:
            rootDir = Path(root)

        if not rootDir.is_dir():
            return

        name = self.nameInput('Directory name')
        if name:
            dirpath = rootDir.joinpath(name)
            if dirpath.exists():
                return messageBox('Already exists')

            dirpath.mkdir()
            self.localCheckoutChanged = True
            self.sessionViewUpdate()

    def onFsViewItemDoubleClicked(self, idx, fInfo):
        fullPath = fInfo.absoluteFilePath()

        if not self.checkoutPath:
            return

        if not os.path.isfile(fullPath):
            return

        filepath = re.sub(self.checkoutPath, '', fullPath).lstrip('/')
        ensure(self.openFileFromCheckout(filepath))

    def onDocumentChanged(self):
        if self.previewWidget.isVisible():
            self._previewTimer.stop()
            self._previewTimer.start(1200)

    def onEditorViewToggled(self, toggle):
        if self.previewButton.isChecked():
            self.textEditor.setVisible(toggle)
        else:
            self.editorViewButton.setChecked(True)

    def onPreviewRerender(self):
        ensure(self.updatePreview())
        self._previewTimer.stop()

    def showNameInput(self, view=True):
        self.nameInputLabel.setVisible(view)
        self.nameInputLine.setVisible(view)
        self.nameInputValidate.setVisible(view)

        if view is False:
            self.nameInputLine.clear()

        if view is True:
            self.nameInputLine.setFocus(Qt.OtherFocusReason)

    def onTabReplaceToggled(self, state):
        self.textEditor.tabReplace = state

    def onNameInput(self):
        filename = self.nameInputLine.text()
        if len(filename) > 0:
            self.filenameEntered.emit(filename)

    def onFilenameEntered(self, filename):
        if self.currentDocument:
            self.currentDocument.filename = filename
            self.currentDocument.filenameChanged.emit(filename)

            self.documentNameChanged.emit(self.currentDocument, filename)
            self.showNameInput(False)
            ensure(self.saveDocument(self.currentDocument))

    def onDocnameChanged(self, doc, name):
        if doc == self.currentDocument:
            self.setTabName(name, widget=self)

    def applyStylesheet(self):
        if self.editing is True:
            self.textEditor.setStyleSheet('''
                QPlainTextEdit {
                    background-color: #D2DBD6;
                    color: #242424;
                    padding: 5px;
                    font: 14pt "Courier";
                    font-weight: bold;
                }
            ''')
            self.textEditor.connectSignals()
        else:
            self.textEditor.highlightCurrentLine()
            self.textEditor.setStyleSheet(defaultStyleSheet)

    def display(self, ipfsPath):
        if not isinstance(ipfsPath, IPFSPath) or not ipfsPath.valid:
            return

        ensure(self.showFromPath(ipfsPath))

    def genUid(self):
        return str(uuid.uuid4())

    def newDocument(self, name=None, text='', encoding='utf-8',
                    textLayout=True):
        self.textEditor.setStyleSheet(defaultStyleSheet)
        doc = Document(name=name, text=text, parent=self, encoding=encoding,
                       textLayout=textLayout)
        doc._previewDocument = Document(parent=doc, textLayout=False)
        return doc

    async def updatePreview(self):
        textData = self.currentDocument.toPlainText()
        pDocument = self.currentDocument.previewDocument

        try:
            mimeType = await detectMimeTypeFromBuffer(textData.encode())
        except:
            pass

        if self.currentDocument.filename:
            await self.writeDocument(self.currentDocument)

        if mimeType and mimeType.isHtml:
            if self.currentDocument.filename:
                url = self.checkoutChildFileUrl(self.currentDocument.filename)
                self.previewWidget.setUrl(url)
            else:
                self.previewWidget.setHtml(textData)
        else:
            try:
                html = markitdown(textData)
                pDocument.setHtml(html)
                self.previewWidget.setHtml(html)
            except Exception:
                pDocument.setPlainText(textData)

    def showPreview(self):
        self.previewWidget.show()
        ensure(self.updatePreview())

    def showText(self, textData, preview=False):
        if preview:
            text = textData
            newDocument = self.newDocument(text=textData)

            try:
                html = markitdown(text)
                newDocument.setHtml(html)
            except Exception:
                newDocument.setPlainText(text)

            self.textEditor.setReadOnly(True)
            return newDocument
        else:
            doc = self.newDocument(text=textData)
            self.textEditor.setReadOnly(not self.editing)
            return doc

    def onFsViewToggled(self, checked):
        self.toggleFsView(checked)

    def toggleFsView(self, view):
        if self.filesView:
            self.filesView.setVisible(view)

    def onSave(self):
        if self.currentDocument.changed:
            if self.currentDocument.filename is None:
                self.showNameInput(True)
            else:
                ensure(self.saveDocument(self.currentDocument))
        else:
            ensure(self.syncSession())

    def nameInput(self, label='File name'):
        name = inputText(label=label)
        if name and len(name) in range(1, 256):
            return name

    async def checkChanges(self):
        if self.currentDocument and self.currentDocument.changed is True:
            return await questionBoxAsync(
                'Unsaved changes',
                'The current document was not saved, continue ?')
        return True

    def onEditToggled(self, checked):
        self.editing = checked

    def onPreviewToggled(self, checked):
        self.inPreview = checked

        if checked:
            self.showPreview()
        else:
            if self.editorViewButton.isChecked():
                self.previewWidget.setVisible(checked)
            else:
                self.previewButton.setChecked(True)

    def onSessionCidChanged(self, cid):
        log.debug('Session now at CID: {}'.format(cid))
        self.unixDirCid = cid
        self.unixDirPath = IPFSPath(cid)
        self.unixDirLabel.path = self.unixDirPath
        self.unixDirClipButton.path = self.unixDirPath

    def sessionViewUpdate(self, root=None):
        path = root if root else self.checkoutPath
        self.model.setRootPath(path)
        self.filesView.setRootIndex(self.model.index(path))

    def sessionNew(self):
        localDirName = self.genUid()
        localPath = os.path.join(
            self.app.tempDir.path(), localDirName)

        if not os.path.exists(localPath):
            try:
                os.mkdir(localPath)
            except:
                pass

        ensure(self.sync())
        self.sessionViewUpdate(localPath)
        self.checkoutPath = localPath
        return localPath

    def makeDatetime(self, date=None):
        datet = date if date else datetime.now()
        return isoformat(datet)

    @ipfsOp
    async def sync(self, ipfsop):
        self.busy(True)
        try:
            entry = await ipfsop.addPath(
                self.checkoutPath,
                wrap=False,
                hidden=True,
                offline=self.offlineModeButton.isChecked()
            )
        except Exception as err:
            self.busy(False)
            log.debug(str(err))
        else:
            self.localCheckoutChanged = False
            self.busy(False)
            if not entry:
                return

            self.rootMultihashChanged.emit(entry['Hash'])
            return entry

    def checkoutChildPath(self, path):
        if self.checkoutPath:
            return Path(os.path.join(self.checkoutPath, path))

    def checkoutChildFileUrl(self, path):
        return QUrl('file://{0}'.format(self.checkoutChildPath(path)))

    async def writeDocument(self, document):
        docPath = self.checkoutChildPath(document.filename)
        text = document.toPlainText()

        async with aiofiles.open(docPath, 'w+t') as fd:
            log.debug('Writing document: {}'.format(docPath))
            await fd.write(text)

    @ipfsOp
    async def onShowDiff(self, ipfsop, path, prevPath, changes, *extra):
        """
        Show the object diff in a QTextBrowser

        TODO: refactor, at least ..
        """

        dlg = QDialog()
        dlg.setWindowTitle(iObjectDiff())
        layout = QVBoxLayout()
        dlg.setLayout(layout)
        dlg.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        dlg.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        dlg.setWindowFlag(Qt.WindowCloseButtonHint, True)
        dlg.setMinimumSize(
            (2 * self.app.desktopGeometry.width()) / 3,
            (2 * self.app.desktopGeometry.height()) / 3,
        )

        dBrowser = QTextBrowser(dlg)
        layout.addWidget(dBrowser)

        async def getTextContent(cid):
            mType = await detectMimeType(cid, bufferSize=1024)
            if mType and mType.isText:
                return await ipfsop.catObject(cid)

        for change in changes:
            objPath = change.get('Path')
            before = change.get('Before')
            after = change.get('After')
            beforeCid = before.get('/') if before else None
            afterCid = after.get('/') if after else None

            if change['Type'] == 2 and beforeCid and afterCid:
                try:
                    _bData = await getTextContent(beforeCid)
                    _aData = await getTextContent(afterCid)

                    if not _bData:
                        dBrowser.insertHtml(
                            '<p>Ignoring object {}</p>'.format(beforeCid))
                        continue

                    if not _aData:
                        dBrowser.insertHtml(
                            '<p>Ignoring object {}</p>'.format(afterCid))
                        continue

                    diff = difflib.HtmlDiff().make_file(
                        _bData.decode().split('\n'),
                        _aData.decode().split('\n'),
                        fromdesc=objPath if objPath else '',
                        todesc=objPath if objPath else '',
                        context=True,
                        numlines=10
                    )

                    dBrowser.insertHtml(diff)
                except Exception:
                    continue
            elif change['Type'] == 0 and afterCid:
                try:
                    _aData = await getTextContent(afterCid)

                    if not _aData:
                        dBrowser.insertHtml(
                            '<p>Ignoring object {}</p>'.format(afterCid))
                        continue

                    lines = _aData.decode().split('\n')

                    diff = difflib.HtmlDiff().make_file(
                        [],
                        lines,
                        fromdesc='',
                        todesc=objPath if objPath else '',
                        context=True,
                        numlines=len(lines)
                    )

                    dBrowser.insertHtml(diff)
                except Exception:
                    continue
            elif change['Type'] == 1 and beforeCid:
                try:
                    _bData = await getTextContent(beforeCid)

                    if not _bData:
                        dBrowser.insertHtml(
                            '<p>Ignoring object {}</p>'.format(beforeCid))
                        continue

                    lines = _bData.decode().split('\n')

                    diff = difflib.HtmlDiff().make_file(
                        lines,
                        [],
                        todesc='',
                        fromdesc=objPath if objPath else '',
                        context=True,
                        numlines=len(lines)
                    )

                    dBrowser.insertHtml(diff)
                except Exception:
                    continue

        dBrowser.moveCursor(QTextCursor.Start)
        dlg.showMaximized()
        await threadExec(dlg.exec_)

    @ipfsOp
    async def saveDocument(self, ipfsop, document, offline=True):
        text = document.toPlainText()

        if not document.filename:
            return

        await self.writeDocument(self.currentDocument)

        self.applyOptionsForDocument()

        if document.previewDocument:
            if filenameIsMarkdown(document.filename):
                document.previewDocument.filename = \
                    document.filename.replace('.md', '.html')

            if document.previewDocument.filename and \
                    self.autoMdHtmlSaveButton.isChecked():
                pPath = os.path.join(self.checkoutPath,
                                     document.previewDocument.filename)
                text = document.previewDocument.toHtml()

                async with aiofiles.open(pPath, 'w+t') as fd:
                    await fd.write(text)

        document.setModified(False)

        self.sessionViewUpdate(self.checkoutPath)

        await self.syncSession()

    @ipfsOp
    async def syncSession(self, ipfsop):
        # Previous session's IPFS path
        prevSessPath = self.unixDirPath

        entry = await self.sync()
        if entry:
            layout = QHBoxLayout()
            path = IPFSPath(entry['Hash'])

            diffButton = None
            if prevSessPath:
                # Generate an object diff tooltip
                changes = await ipfsop.objectDiff(prevSessPath, path)

                if isinstance(changes, list):
                    diffButton = QToolButton()
                    diffButton.setIcon(getIcon('code-fork.png'))
                    diffButton.setToolTip(
                        objectDiffSummaryShort(changes)
                    )
                    diffButton.clicked.connect(
                        partialEnsure(
                            self.onShowDiff,
                            path, prevSessPath, changes
                        )
                    )

            urlLabel = IPFSUrlLabel(path)
            clipButton = IPFSPathClipboardButton(path)
            pyrDropButton = self.app.mainWindow.getPyrDropButtonFor(
                path, origin=self.pyramidOrigin
            )

            now = QDateTime.currentDateTime()
            date = QLabel()
            date.setText(now.toString('hh:mm:ss'))

            hmarkButton = HashmarkThisButton(str(path))

            publishButton = QToolButton()
            publishButton.setText('Publish')
            publishButton.clicked.connect(functools.partial(
                self.onPublishFile, entry, publishButton))

            layout.addWidget(date)
            layout.addWidget(urlLabel)
            layout.addWidget(clipButton)

            if diffButton:
                layout.addWidget(diffButton)

            layout.addWidget(hmarkButton)
            layout.addWidget(pyrDropButton)
            layout.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding,
                                       QSizePolicy.Minimum))

            if self.offlineModeButton.isChecked():
                layout.addWidget(publishButton)

            self.copiesLayout.insertLayout(0, layout)
            self.editHistory.show()

            self.saveButton.setEnabled(False)

    @ipfsOp
    async def publishEntry(self, ipfsop, entry):
        log.debug('Publishing {}'.format(entry))
        try:
            async for msg in ipfsop.client.dht.provide(entry['Hash']):
                log.debug('Provide result: {}'.format(msg))
        except Exception as err:
            messageBox('Could not publish')
            log.debug(str(err))
            return False
        else:
            return True

    def onPublishFile(self, entry, pButton):
        def finished(future):
            try:
                result = future.result()
                if result is True:
                    pButton.setStyleSheet('''
                        QToolButton {
                            color: green;
                        }'''
                                          )
                    pButton.setText('OK')
            except:
                pButton.setText('ERR')

        ensure(self.publishEntry(entry), futcallback=finished)
        pButton.setEnabled(False)
        pButton.setText('Publishing ..')

    @ipfsOp
    async def showFromPath(self, ipfsop, ipfsPath):
        if not await self.checkChanges():
            return

        if not ipfsPath.valid:
            return

        self.busy()

        try:
            dstdir = self.sessionNew()
            mimeType, stat = await self.app.rscAnalyzer(ipfsPath)

            if not stat:
                self.busy(False)
                messageBox('Object stat failed')
                return

            sInfo = StatInfo(stat)

            if not await ipfsop.client.get(
                ipfsPath.objPath,
                dstdir=dstdir
            ):
                raise Exception('Fetch failed')
        except Exception as err:
            self.busy(False)
            messageBox('Error fetching object: {}'.format(str(err)))
        else:
            rooted = os.path.join(dstdir, ipfsPath.basename)

            if os.path.isdir(rooted):
                path = rooted
            elif os.path.isfile(rooted):
                path = dstdir
            else:
                path = dstdir

            self.checkoutPath = path
            self.sessionViewUpdate(self.checkoutPath)

            for file in os.listdir(self.checkoutPath):
                await asyncio.sleep(0)

                fp = os.path.join(self.checkoutPath, file)
                mtype = await detectMimeTypeFromFile(fp)

                # Open first text file we find
                if mtype and (mtype.isText or mtype.isHtml):
                    await self.openFileFromCheckout(file)
                    break

            self.fsViewButton.setChecked(True)
            self.rootMultihashChanged.emit(sInfo.cid)

        self.busy(False)

    async def isTextFile(self, path):
        mtype = await detectMimeTypeFromFile(path)
        return mtype and (mtype.isText or mtype.isHtml)

    async def openFileFromCheckout(self, relpath):
        if not await self.checkChanges():
            return

        self.previewButton.setChecked(False)
        fp = Path(os.path.join(self.checkoutPath, relpath))

        if not fp.exists():
            return

        fsize = fp.stat().st_size

        if fsize > 0 and not await self.isTextFile(str(fp)):
            return messageBox('Not a text file')

        self.busy()

        basename = relpath
        doc = self.newDocument(name=basename)
        cursor = QTextCursor(doc)

        async for chunk in asyncReadTextFileChunked(
                str(fp), mode='rt'):
            await asyncio.sleep(0.1)
            cursor.insertText(chunk)

        self.currentDocument = doc
        self.busy(False)
        return doc

    def decode(self, data):
        for enc in ['utf-8', 'latin1', 'ascii']:
            try:
                textData = data.decode(enc)
            except BaseException:
                continue
            else:
                return enc, textData
        return None, None
