import functools
import aiofiles
import os.path
import json
import os
import uuid
from datetime import datetime

from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QScrollArea
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtWidgets import QSpacerItem
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QFrame
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QLineEdit

from PyQt5.QtCore import QDateTime
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QRegularExpression
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QDir
from PyQt5.QtCore import QTimer

from PyQt5.QtGui import QTextDocument
from PyQt5.QtGui import QTextFormat
from PyQt5.QtGui import QColor
from PyQt5.QtGui import QSyntaxHighlighter
from PyQt5.QtGui import QTextCharFormat
from PyQt5.QtGui import QFont

from galacteek import log
from galacteek.ipfs.ipfsops import *
from galacteek.core import isoformat
from galacteek.appsettings import *
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.dweb.markdown import markitdown

from .helpers import *

from .ipfsview import IPFSHashExplorerWidgetFollow
from .widgets import PopupToolButton
from .widgets import IPFSPathClipboardButton
from .widgets import IPFSUrlLabel
from .widgets import GalacteekTab
from .widgets import CheckableToolButton
from .i18n import *


def iSave():
    return QCoreApplication.translate('textEditor',
                                      'Save')


def iEdit():
    return QCoreApplication.translate('textEditor',
                                      'Edit')


def iMarkdownPreview():
    return QCoreApplication.translate('textEditor',
                                      'Markdown preview')


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
    QTextEdit {
        padding: 5px;
        color: #242424;
        background-color: #F0F7F7;
        font: 11pt "Courier";
    }
'''


class Editor(QTextEdit):
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

    def __init__(self, encoding=None, name=None, text='', parent=None):
        super().__init__(text, parent)

        self._filename = name
        self._changed = False
        self._encoding = encoding if encoding else 'utf-8'
        self.setDefaultStyleSheet(defaultStyleSheet)
        self.setModified(False)
        self.modificationChanged.connect(self.onModifChange)

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
    def __init__(self, editing=False, parent=None):
        super(TextEditorTab, self).__init__(parent)

        self.editor = TextEditorWidget(
            editing=editing,
            parent=self)
        self.editor.documentChanged.connect(self.onDocChange)
        self.editor.documentNameChanged.connect(self.onDocnameChanged)

        self.vLayout.addWidget(self.editor)

    def onDocChange(self, doc):
        self.setTabName(doc.filename, widget=self)

    def onDocnameChanged(self, doc, name):
        if doc is self.editor.currentDocument:
            self.setTabName(name, widget=self)

    def onClose(self):
        if self.editor.checkChanges() is True:
            return True
        return False


class TextEditorWidget(QWidget):
    """
    Simple Editor widget that stores the edited files in a unixfs node
    """

    rootMultihashChanged = pyqtSignal(str)
    documentChanged = pyqtSignal(Document)
    documentNameChanged = pyqtSignal(Document, str)
    filenameEntered = pyqtSignal(str)

    def __init__(self, offline=True, editing=False, sessionDagCid=None,
                 parent=None):
        super(TextEditorWidget, self).__init__(parent)

        self.app = QApplication.instance()
        self.setLayout(QVBoxLayout(self))
        self.textEditor = Editor(self)

        self.localDirName = self.genUid()
        self.localPath = os.path.join(
            self.app.tempDir.path(), self.localDirName)
        self.localDir = QDir(self.localPath)

        self._previewTimer = QTimer(self)
        self._previewTimer.timeout.connect(self.onPreviewRerender)
        self._editing = editing
        self._currentDocument = None
        self._unixDir = None

        self.setObjectName('textEditor')
        self.inPreview = False
        self.offline = offline

        self.editHistory = EditHistory(parent=self)
        self.editHistory.hide()
        self.copiesLayout = self.editHistory.fLayout

        self.ctrlLayout = QHBoxLayout()

        self.previewButton = CheckableToolButton(
            icon=getIcon('document-preview.png'),
            toggled=self.onPreviewToggled, parent=self
        )
        self.previewButton.setToolTip(iMarkdownPreview())

        self.fsViewButton = CheckableToolButton(
            icon=getIcon('folder-open.png'),
            toggled=self.onFsViewToggled, parent=self
        )
        self.fsViewButton.setEnabled(False)

        self.editButton = CheckableToolButton(
            toggled=self.onEditToggled, parent=self
        )

        self.saveButton = QToolButton()
        self.saveButton.setIcon(getIcon('save-file.png'))
        self.saveButton.clicked.connect(self.onSave)
        self.saveButton.setToolTip(iSave())
        self.saveButton.setEnabled(False)

        strokeIcon = getIcon('stroke-cube.png')
        self.fsControlButton = PopupToolButton(
            mode=QToolButton.InstantPopup,
            icon=strokeIcon
        )
        self.fsControlButton.setEnabled(False)

        self.fsControlButton.menu.addAction(
            strokeIcon, 'New file', self.onNewFile)

        self.editButton.setText(iEdit())

        self.unixDirCid = None
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

        self.ctrlLayout.addWidget(self.fsControlButton)
        self.ctrlLayout.addWidget(self.editButton)
        self.ctrlLayout.addWidget(self.previewButton)
        self.ctrlLayout.addWidget(self.fsViewButton)
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

        self.previewWidget = QTextEdit(self)
        self.previewWidget.hide()

        self.currentDocument = self.newDocument()
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

        self.filesView = None
        self.rootMultihashChanged.connect(self.onSessionCidChanged)

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

        if self.editing is True and self.unixDirCid is None:
            ensure(self.sessionNew())

    @property
    def currentDocument(self):
        return self._currentDocument

    @currentDocument.setter
    def currentDocument(self, doc):
        self._currentDocument = doc
        self.textEditor.setDocument(self.currentDocument)

        if self.currentDocument.filename:
            if self.currentDocument.filename.endswith('.py'):
                self.highlighter = PythonSyntaxHighlighter(
                    self.currentDocument)
                self.tabReplaceButton.setChecked(True)
        else:
            self.highlighter = None

        self.documentChanged.emit(self.currentDocument)
        self.currentDocument.setModified(False)

        self.currentDocument.modified.connect(
            functools.partial(self.saveButton.setEnabled, True))
        self.currentDocument.contentsChanged.connect(self.onDocumentChanged)

        self.applyStylesheet()

    def onDocumentChanged(self):
        if self.previewWidget.isVisible():
            self._previewTimer.stop()
            self._previewTimer.start(1200)

    def onPreviewRerender(self):
        self.markdownPreviewUpdate()
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
                QTextEdit {
                    background-color: #D2DBD6;
                    color: #242424;
                    padding: 5px;
                    font: 12pt "Courier";
                    font-weight: bold;
                }
            ''')
            self.textEditor.connectSignals()
        else:
            self.textEditor.highlightCurrentLine()
            self.textEditor.setStyleSheet(defaultStyleSheet)

    @property
    def unixDirCid(self):
        return self._unixDirCid

    @property
    def unixDir(self):
        return self._unixDir

    @unixDirCid.setter
    def unixDirCid(self, cid):
        self._unixDirCid = cid

    def display(self, ipfsPath):
        if not isinstance(ipfsPath, IPFSPath) or not ipfsPath.valid:
            return

        ensure(self.showFromPath(ipfsPath))

    def genUid(self):
        return str(uuid.uuid4())

    def newDocument(self, name=None, text='', encoding='utf-8'):
        self.textEditor.setStyleSheet(defaultStyleSheet)
        return Document(name=name, text=text, parent=self, encoding=encoding)

    def markdownPreviewUpdate(self):
        textData = self.currentDocument.toPlainText()
        pDocument = self.previewWidget.document()

        try:
            html = markitdown(textData)
            pDocument.setHtml(html)
        except Exception:
            pDocument.setPlainText(textData)

    def showPreview(self):
        textData = self.currentDocument.toPlainText()
        newDocument = self.newDocument(text=textData)

        try:
            html = markitdown(textData)
            newDocument.setHtml(html)
        except Exception:
            newDocument.setPlainText(textData)

        self.previewWidget.setDocument(newDocument)
        self.previewWidget.setReadOnly(True)
        self.previewWidget.show()

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
        if self.currentDocument.filename is None:
            self.showNameInput(True)
        else:
            ensure(self.saveDocument(self.currentDocument))

    def nameInput(self, label='File name'):
        name = inputText(label=label)
        if name and len(name) in range(1, 256):
            return name

    def onNewDirectory(self):
        name = self.nameInput(label='Directory name')

        if name:
            self.localDir.mkdir(name)
            ensure(self.sync())

    def checkChanges(self):
        if self.currentDocument and self.currentDocument.changed is True:
            reply = questionBox(
                'Unsaved changes',
                'The current document was not saved, continue ?')
            return reply
        return True

    def onNewFile(self):
        if not self.checkChanges():
            return

        name = self.nameInput()

        if name:
            self.currentDocument = self.newDocument(name=name)
            self.editing = True

    def onEditToggled(self, checked):
        self.editing = checked

    def onPreviewToggled(self, checked):
        self.inPreview = checked

        if checked:
            self.showPreview()
        else:
            self.previewWidget.hide()

    def onSessionCidChanged(self, cid):
        log.debug('Session now at CID: {}'.format(cid))
        self.unixDirCid = cid
        self.unixDirPath = IPFSPath(cid)
        self.unixDirLabel.path = self.unixDirPath
        self.unixDirClipButton.path = self.unixDirPath

        if not self.filesView:
            self.filesView = IPFSHashExplorerWidgetFollow(
                cid, parent=self,
                addActions=False,
                autoOpenFiles=False,
                mimeDetectionMethod='magic')
            self.filesView.fileOpenRequest.connect(
                self.onFilesViewOpen)
            self.filesView.setMaximumWidth(self.width() / 3)
            self.textHLayout.addWidget(self.filesView)
            self.fsViewButton.setEnabled(True)
            self.fsViewButton.setChecked(True)
        else:
            if self.filesView.rootHash != cid:
                self.filesView.parentHash = None
                self.filesView.changeMultihash(cid)
                self.filesView.updateTree()

    def onFilesViewOpen(self, ipfsPath):
        ensure(self.showFromPath(ipfsPath))

    @ipfsOp
    async def sessionNew(self, ipfsop):
        if not os.path.exists(self.localPath):
            try:
                os.mkdir(self.localPath)
            except:
                pass

        p = os.path.join(self.localPath, '.info')
        datet = datetime.now()
        async with aiofiles.open(p, 'w+t') as fd:
            await fd.write(json.dumps({
                'created': isoformat(datet)
            }))

        await self.sync()
        self.fsControlButton.setEnabled(True)

    def makeDatetime(self, date=None):
        datet = date if date else datetime.now()
        return isoformat(datet)

    @ipfsOp
    async def sync(self, ipfsop):
        try:
            async with ipfsop.offlineMode() as opoff:
                entry = await opoff.addPath(self.localPath, wrap=False,
                                            hidden=True)
        except Exception as err:
            log.debug(str(err))
        else:
            if not entry:
                return

            self.rootMultihashChanged.emit(entry['Hash'])
            return entry

    @ipfsOp
    async def saveDocument(self, ipfsop, document, offline=True):
        text = document.toPlainText()

        if not document.filename:
            return

        docPath = os.path.join(self.localPath, document.filename)
        async with aiofiles.open(docPath, 'w+t') as fd:
            await fd.write(text)

        document.setModified(False)
        self.saveButton.setEnabled(False)

        entry = await self.sync()
        if entry:
            layout = QHBoxLayout()
            path = IPFSPath(entry['Hash'])

            urlLabel = IPFSUrlLabel(path)
            clipButton = IPFSPathClipboardButton(path)

            now = QDateTime.currentDateTime()
            date = QLabel()
            date.setText(now.toString('hh:mm:ss'))

            publishButton = QToolButton()
            publishButton.setText('Publish')
            publishButton.clicked.connect(functools.partial(
                self.onPublishFile, entry, publishButton))

            layout.addWidget(date)
            layout.addWidget(urlLabel)
            layout.addWidget(clipButton)
            layout.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding,
                           QSizePolicy.Minimum))
            layout.addWidget(publishButton)

            self.copiesLayout.insertLayout(0, layout)
            self.editHistory.show()

    @ipfsOp
    async def publishEntry(self, ipfsop, entry):
        log.debug('Publishing {}'.format(entry))
        try:
            async for msg in ipfsop.client.dht.provide(entry['Hash']):
                log.debug('Provide result: {}'.format(msg))
        except Exception:
            log.debug('Publish error')
            return False
        else:
            return True

    def onPublishFile(self, entry, pButton):
        def finished(future):
            try:
                result = future.result()
                if result is True:
                    pButton.setEnabled(False)
                    pButton.setText('Published')
            except:
                pButton.setText('ERR')

        ensure(self.publishEntry(entry),
               futcallback=finished)

    @ipfsOp
    async def showFromPath(self, ipfsop, ipfsPath):
        if not self.checkChanges():
            return

        if not ipfsPath.valid:
            return

        data = await ipfsop.client.cat(ipfsPath.objPath)

        if not data:
            return messageBox('File could not be read')

        self.showNameInput(False)

        encoding, textData = self.decode(data)

        doc = self.newDocument(name=ipfsPath.basename, text=textData,
                               encoding=encoding)
        self.currentDocument = doc

    def decode(self, data):
        for enc in ['utf-8', 'latin1', 'ascii']:
            try:
                textData = data.decode(enc)
            except BaseException:
                continue
            else:
                return enc, textData
        return None, None
