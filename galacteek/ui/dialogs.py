import aioipfs

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QDialogButtonBox
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QGridLayout
from PyQt5.QtWidgets import QFormLayout
from PyQt5.QtWidgets import QAbstractItemView
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QSpinBox

from PyQt5.QtCore import QSize
from PyQt5.QtCore import QFile
from PyQt5.QtCore import QIODevice
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import QRegExp
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QStringListModel
from PyQt5.QtCore import QSortFilterProxyModel

from PyQt5.QtGui import QClipboard
from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QRegExpValidator

from galacteek import GALACTEEK_NAME
from galacteek import ensure
from galacteek import logUser
from galacteek import database

from galacteek.core.ipfsmarks import *
from galacteek.core.ipfsmarks import categoryValid
from galacteek.core.iptags import ipTagsFormat
from galacteek.ipfs import cidhelpers
from galacteek.ipfs.ipfsops import *
from galacteek.ipfs.wrappers import ipfsOp

from . import ui_addhashmarkdialog
from . import ui_addfeeddialog
from . import ui_ipfscidinputdialog, ui_ipfsmultiplecidinputdialog
from . import ui_donatedialog
from . import ui_qschemecreatemapping
from . import ui_iptagsmanager
from . import ui_mfsoptionsdialog

from .helpers import *
from .widgets import ImageWidget
from .widgets import HorizontalLine
from .widgets import IconSelector
from .widgets import LabelWithURLOpener

from .i18n import iTitle
from .i18n import iDoNotPin
from .i18n import iPinSingle
from .i18n import iPinRecursive
from .i18n import iNoTitleProvided
from .i18n import iNoCategory
from .i18n import iHashmarkIPTagsEdit
from .i18n import iDownload
from .i18n import iDownloadOpenDialog
from .i18n import iOpen


def boldLabelStyle():
    return 'QLabel { font-weight: bold; }'


class AddHashmarkDialog(QDialog):
    def __init__(
            self,
            resource,
            title,
            description,
            pin=False,
            pinRecursive=False,
            schemePreferred=None,
            parent=None):
        super().__init__(parent)

        self.ipfsResource = resource
        self.iconCid = None
        self.schemePreferred = schemePreferred

        self.ui = ui_addhashmarkdialog.Ui_AddHashmarkDialog()
        self.ui.setupUi(self)
        self.ui.resourceLabel.setText(self.ipfsResource)
        self.ui.resourceLabel.setStyleSheet(boldLabelStyle())
        self.ui.resourceLabel.setToolTip(self.ipfsResource)
        self.ui.newCategory.textChanged.connect(self.onNewCatChanged)
        self.ui.title.setText(title)
        self.ui.share.hide()

        pix = QPixmap.fromImage(QImage(':/share/icons/hashmarks.png'))
        pix = pix.scaledToWidth(32)
        self.ui.hashmarksIconLabel.setPixmap(pix)

        self.iconWidget = None

        self.ui.pinCombo.addItem(iDoNotPin())
        self.ui.pinCombo.addItem(iPinSingle())
        self.ui.pinCombo.addItem(iPinRecursive())

        self.ui.formLayout.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self.ui.formLayout.setFieldGrowthPolicy(
            QFormLayout.ExpandingFieldsGrow)
        self.ui.formLayout.setLabelAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.ui.formLayout.setHorizontalSpacing(20)

        self.iconSelector = IconSelector(parent=self, allowEmpty=True)
        self.iconSelector.iconSelected.connect(self.onIconSelected)
        self.iconSelector.emptyIconSelected.connect(self.onIconEmpty)
        self.ui.formLayout.insertRow(7, QLabel('Icon'),
                                     self.iconSelector)

        regexp1 = QRegExp(r"[A-Za-z0-9/\-]+")  # noqa
        self.ui.newCategory.setValidator(QRegExpValidator(regexp1))
        self.ui.newCategory.setMaxLength(64)

        if pin is True:
            self.ui.pinCombo.setCurrentIndex(1)
        elif pinRecursive is True:
            self.ui.pinCombo.setCurrentIndex(2)

        if isinstance(description, str):
            self.ui.description.insertPlainText(description)

    async def initDialog(self):
        await self.fillCategories()

    async def fillCategories(self):
        self.ui.category.addItem(iNoCategory())
        self.ui.category.insertSeparator(0)

        for cat in await database.categoriesNames():
            self.ui.category.addItem(cat)

    def onIconSelected(self, iconCid):
        self.iconCid = iconCid

    def onIconEmpty(self):
        self.iconCid = None

    def onSelectIcon(self):
        fps = filesSelectImages()
        if len(fps) > 0:
            ensure(self.setIcon(fps.pop()))

    @ipfsOp
    async def setIcon(self, op, fp):
        entry = await op.addPath(fp, recursive=False)
        if entry:
            cid = entry['Hash']

            if self.iconWidget is None:
                iconWidget = ImageWidget()

                if await iconWidget.load(cid):
                    self.ui.formLayout.insertRow(7, QLabel(''), iconWidget)
                    self.iconCid = cid
                    self.iconWidget = iconWidget
            else:
                if await self.iconWidget.load(cid):
                    self.iconCid = cid

    def onNewCatChanged(self, text):
        self.ui.category.setEnabled(len(text) == 0)

    def accept(self):
        ensure(self.process())

    async def process(self):
        title = self.ui.title.text()

        if len(title) == 0:
            return messageBox(iNoTitleProvided())

        share = self.ui.share.isChecked()
        newCat = self.ui.newCategory.text()
        description = self.ui.description.toPlainText()

        if len(description) > 1024:
            return messageBox('Description is too long')

        if len(newCat) > 0:
            category = cidhelpers.normp(newCat)
        elif self.ui.category.currentText() != iNoCategory():
            category = self.ui.category.currentText()
        else:
            category = None

        hashmark = await database.hashmarkAdd(
            self.ipfsResource,
            title=title,
            comment=self.ui.comment.text(),
            description=description,
            icon=self.iconCid,
            category=category,
            share=share,
            pin=self.ui.pinCombo.currentIndex(),
            schemepreferred=self.schemePreferred
        )

        self.done(0)

        await runDialogAsync(
            HashmarkIPTagsDialog,
            hashmark=hashmark
        )


class AddFeedDialog(QDialog):
    def __init__(self, marks, resource, feedName=None, parent=None):
        super().__init__(parent)

        self.marks = marks
        self.ipfsResource = resource

        self.ui = ui_addfeeddialog.Ui_AddFeedDialog()
        self.ui.setupUi(self)
        self.ui.resourceLabel.setText(self.ipfsResource)
        self.ui.resourceLabel.setStyleSheet(boldLabelStyle())

        self.ui.formLayout.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self.ui.formLayout.setFieldGrowthPolicy(
            QFormLayout.ExpandingFieldsGrow)
        self.ui.formLayout.setLabelAlignment(Qt.AlignCenter)
        self.ui.formLayout.setHorizontalSpacing(20)

        if isinstance(feedName, str):
            self.ui.feedName.setText(feedName)

    def accept(self):
        ensure(self.addFeed())

    async def addFeed(self):
        autoPin = self.ui.autoPin.isChecked()
        feedName = self.ui.feedName.text()

        if len(feedName) == 0:
            return messageBox('Please specify a feed name')

        mark = await database.hashmarkAdd(
            self.ipfsResource,
            tags=['#ipnsfeed']
        )
        mark.follow = True

        feed = database.IPNSFeed(
            name=feedName, autopin=autoPin,
            feedhashmark=mark,
            resolveevery=self.ui.resolve.value()
        )
        await mark.save()
        await feed.save()

        self.done(0)


class IPFSCIDInputDialog(QDialog):
    """ Dialog for IPFS CID input and validation """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.validCid = False
        self.ui = ui_ipfscidinputdialog.Ui_CIDInputDialog()
        self.ui.setupUi(self)
        self.ui.validity.setStyleSheet(boldLabelStyle())
        self.ui.cid.textChanged.connect(self.onCIDChanged)
        self.ui.clearButton.clicked.connect(self.onClearCID)

    def onClearCID(self):
        self.clearCID()

    def clearCID(self):
        """ Clears the CID input text """
        self.ui.cid.clear()

    def onCIDChanged(self, text):
        """
        When the CID input text changes we verify if it's a valid CID and
        update the validity label
        """
        if cidhelpers.cidValid(text):
            cid = self.getCID()
            if cid:
                self.ui.validity.setText(
                    'Valid CID version {}'.format(cid.version))
                self.validCid = True
            else:
                # Unlikely
                self.ui.validity.setText('Unknown CID type')
                self.validCid = False
        else:
            self.ui.validity.setText('Invalid CID')
            self.validCid = False

    def getHash(self):
        """ Returns the hash corresponding to the input, if valid """
        cid = self.getCID()
        if cid:
            return str(cid)

    def getCID(self):
        """ Returns the CID object corresponding to the input """
        try:
            return cidhelpers.getCID(self.ui.cid.text())
        except BaseException:
            return None

    def accept(self):
        if self.validCid is True:
            self.done(1)


class IPFSMultipleCIDInputDialog(QDialog):
    """ Dialog for multiple IPFS CID input """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.validCid = False
        self.ui = ui_ipfsmultiplecidinputdialog.Ui_MultipleCIDInputDialog()
        self.ui.setupUi(self)
        self.ui.validity.setStyleSheet(boldLabelStyle())
        self.ui.cid.textChanged.connect(self.onCIDChanged)
        self.ui.addCidButton.clicked.connect(self.onAddCID)

    def onAddCID(self):
        if self.validCid:
            self.ui.cidList.addItem(self.ui.cid.text())
            self.ui.cid.clear()

    def onCIDChanged(self, text):
        if cidhelpers.cidValid(text):
            self.ui.validity.setText('Valid CID')
            self.validCid = True
        else:
            self.ui.validity.setText('Invalid CID')
            self.validCid = False

    def getCIDs(self):
        cids = []
        for idx in range(0, self.ui.cidList.count()):
            item = self.ui.cidList.item(idx)
            cids.append(item.text())
        return cids

    def accept(self):
        self.done(1)


class DonateDialog(QDialog):
    def __init__(self, bcAddr, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.ui = ui_donatedialog.Ui_DonateDialog()
        self.ui.setupUi(self)
        self.ui.okButton.clicked.connect(self.close)
        self.ui.bitcoinClip.clicked.connect(self.onBcClip)
        self.ui.donatePatreon.clicked.connect(self.onPatreonClicked)

        self._bcAddr = bcAddr
        self.ui.bitcoinAddress.setText('<b>{0}</b>'.format(self._bcAddr))
        self.setWindowTitle('Make a donation')

    def onPatreonClicked(self):
        tab = self.app.mainWindow.addBrowserTab()
        tab.enterUrl(QUrl(
            'https://www.patreon.com/{0}'.format(GALACTEEK_NAME)))
        self.accept()

    def onBcClip(self):
        self.toClip(self._bcAddr)

    def toClip(self, data):
        app = QCoreApplication.instance()
        app.clipboard().setText(data, QClipboard.Selection)
        app.clipboard().setText(data, QClipboard.Clipboard)

    def close(self):
        self.done(1)

    def accept(self):
        self.done(1)


class ChooseProgramDialog(QInputDialog):
    def __init__(self, cmd=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle('Choose a program')
        self.setInputMode(QInputDialog.TextInput)
        self.setLabelText(
            '''Command arguments (example: <b>mupdf %f</b>).
                <b>%f</b> is replaced with the file path''')

        if cmd:
            self.setTextValue(cmd)


class AddAtomFeedDialog(QInputDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle('Add an Atom feed')
        self.setInputMode(QInputDialog.TextInput)
        self.setLabelText('Atom feed URL')

    def sizeHint(self):
        return QSize(600, 140)


class AddMultihashPyramidDialog(QDialog):
    def __init__(self, marks, pyramidType, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()

        self.marks = marks
        self.pyramidType = pyramidType
        self.iconCid = None
        self.customCategory = 'general'
        self.autoSyncPath = None

        label = QLabel('Pyramid name')
        restrictRegexp = QRegExp("[0-9A-Za-z-_]+")  # noqa
        restrictRegexp2 = QRegExp("[0-9A-Za-z-_/]+")  # noqa

        self.nameLine = QLineEdit()
        self.nameLine.setMaxLength(32)
        self.nameLine.setValidator(QRegExpValidator(restrictRegexp))
        label.setBuddy(self.nameLine)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttonBox.setCenterButtons(True)

        catCustomLabel = QLabel('Or create new category')
        catCustomLayout = QHBoxLayout()

        self.catCustom = QLineEdit()
        self.catCustom.setMaxLength(32)
        self.catCustom.setValidator(QRegExpValidator(restrictRegexp2))
        self.catCustom.textChanged.connect(self.onCustomCategory)
        catCustomLabel.setBuddy(self.catCustom)
        catCustomLayout.addWidget(catCustomLabel)
        catCustomLayout.addWidget(self.catCustom)

        descrLabel = QLabel('Description')
        self.descrLine = QLineEdit()
        self.descrLine.setMaxLength(128)
        descrLabel.setBuddy(self.descrLine)
        descrLayout = QHBoxLayout()
        descrLayout.addWidget(descrLabel)
        descrLayout.addWidget(self.descrLine)

        nameLayout = QHBoxLayout()
        nameLayout.addWidget(label)
        nameLayout.addWidget(self.nameLine)

        extraLayout = QVBoxLayout()

        if pyramidType == MultihashPyramid.TYPE_AUTOSYNC:
            layout1 = QHBoxLayout()
            layout2 = QHBoxLayout()

            self.checkBoxHiddenFiles = QCheckBox('Import hidden files')
            self.checkBoxHiddenFiles.setCheckState(Qt.Unchecked)
            self.checkBoxFileStore = QCheckBox('Use Filestore if available')
            self.checkBoxFileStore.setCheckState(Qt.Unchecked)
            self.checkBoxUnpinPrev = QCheckBox('Unpin old content')
            self.checkBoxUnpinPrev.setCheckState(Qt.Unchecked)
            self.checkBoxDirWrap = QCheckBox('Wrap with directory')
            self.checkBoxDirWrap.setCheckState(Qt.Unchecked)
            self.checkBoxStartupSync = QCheckBox('Sync on startup')
            self.checkBoxStartupSync.setCheckState(Qt.Unchecked)

            self.spinBoxSyncDelay = QSpinBox()
            self.spinBoxSyncDelay.setMinimum(1)
            self.spinBoxSyncDelay.setMaximum(3600)
            self.spinBoxSyncDelay.setValue(10)

            self.ignRulesPath = QLineEdit()
            self.ignRulesPath.setMaxLength(32)
            self.ignRulesPath.setText('.gitignore')

            layout1.addWidget(QLabel('Import delay (seconds)'))
            layout1.addWidget(self.spinBoxSyncDelay)

            layout2.addWidget(QLabel('Ignore rules path'))
            layout2.addWidget(self.ignRulesPath)

            labelOr = QLabel('or')
            labelOr.setAlignment(Qt.AlignCenter)

            self.syncDirButton = QPushButton('Choose a directory to auto-sync')
            self.syncDirButton.clicked.connect(self.onChooseSyncDir)
            self.syncFileButton = QPushButton('Choose a file to auto-sync')
            self.syncFileButton.clicked.connect(self.onChooseSyncFile)
            self.syncPathLabel = QLabel('No path selected')
            self.syncPathLabel.setAlignment(Qt.AlignCenter)
            extraLayout.addWidget(self.syncPathLabel)
            extraLayout.addWidget(self.syncDirButton)
            extraLayout.addWidget(labelOr)
            extraLayout.addWidget(self.syncFileButton)
            extraLayout.addWidget(self.checkBoxHiddenFiles)
            extraLayout.addWidget(self.checkBoxDirWrap)
            extraLayout.addWidget(self.checkBoxFileStore)
            extraLayout.addWidget(self.checkBoxStartupSync)
            extraLayout.addLayout(layout1)
            extraLayout.addLayout(layout2)

        self.iconSelector = IconSelector()
        self.iconSelector.iconSelected.connect(self.onIconSelected)

        self.lifetimeCombo = QComboBox(self)
        self.lifetimeCombo.addItem('24h')
        self.lifetimeCombo.addItem('48h')
        self.lifetimeCombo.addItem('96h')
        self.lifetimeCombo.setCurrentText('48h')
        ipnsLTimeLayout = QHBoxLayout()
        ipnsLTimeLayout.addWidget(QLabel('IPNS record lifetime'))
        ipnsLTimeLayout.addWidget(self.lifetimeCombo)

        pickIconLayout = QHBoxLayout()
        pickIconLayout.addWidget(QLabel('Choose an icon'))
        pickIconLayout.addWidget(self.iconSelector)

        mainLayout = QGridLayout()
        mainLayout.addLayout(nameLayout, 0, 0)
        mainLayout.addLayout(descrLayout, 1, 0)
        mainLayout.addWidget(HorizontalLine(self), 2, 0)
        mainLayout.addLayout(extraLayout, 3, 0)
        mainLayout.addWidget(HorizontalLine(self), 4, 0)
        mainLayout.addLayout(ipnsLTimeLayout, 5, 0)
        mainLayout.addLayout(pickIconLayout, 6, 0)
        mainLayout.addWidget(buttonBox, 7, 0)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        self.setLayout(mainLayout)

        self.nameLine.setFocus(Qt.OtherFocusReason)

        self.setMinimumWidth(
            self.app.desktopGeometry.width() / 3
        )
        self.setWindowIcon(getIcon('pyramid-aqua.png'))

    def onChooseSyncDir(self):
        path = directorySelect()
        if path:
            self.autoSyncPath = path
            self.syncPathLabel.setText(path)

    def onChooseSyncFile(self):
        path = fileSelect()
        if path:
            self.autoSyncPath = path
            self.syncPathLabel.setText(path)

    def onIconSelected(self, iconCid):
        self.iconCid = iconCid

    def onCustomCategory(self, text):
        self.categoryCombo.setEnabled(len(text) == 0)
        self.customCategory = text

    def reject(self):
        self.done(0)

    def accept(self):
        extra = {}
        pyramidName = self.nameLine.text()
        descr = self.descrLine.text()
        lifetime = self.lifetimeCombo.currentText()

        if len(pyramidName) == 0:
            return messageBox('Please specify the pyramid name')

        if isinstance(self.customCategory, str) and \
                categoryValid(self.customCategory):
            category = self.customCategory
        else:
            category = self.categoryCombo.currentText()

        if self.pyramidType == MultihashPyramid.TYPE_AUTOSYNC:
            if self.autoSyncPath is None:
                return messageBox(
                    'Please select a file/directory to auto-sync')

            extra['autosyncpath'] = self.autoSyncPath
            extra['syncdelay'] = self.spinBoxSyncDelay.value() * 1000
            extra['importhidden'] = self.checkBoxHiddenFiles.isChecked()
            extra['ignorerulespath'] = self.ignRulesPath.text().strip()
            extra['usefilestore'] = self.checkBoxFileStore.isChecked()
            extra['dirwrapper'] = self.checkBoxDirWrap.isChecked()
            extra['unpinprevious'] = self.checkBoxUnpinPrev.isChecked()
            extra['startupsync'] = self.checkBoxStartupSync.isChecked()

        ipnsKeyName = 'galacteek.pyramids.{cat}.{name}'.format(
            cat=category.replace('/', '_'), name=pyramidName)

        self.done(1)

        ensure(self.createPyramid(pyramidName, category, ipnsKeyName,
                                  descr, lifetime, extra))

    @ipfsOp
    async def createPyramid(self, ipfsop, pyramidName, category, ipnsKeyName,
                            description, ipnsLifetime, extra):
        try:
            logUser.info(
                'Multihash pyramid {pyr}: generating IPNS key ...'.format(
                    pyr=pyramidName))
            ipnsKey = await ipfsop.keyGen(ipnsKeyName)

            if ipnsKey:
                self.marks.pyramidNew(
                    pyramidName, category, self.iconCid,
                    ipnskey=ipnsKey['Id'],
                    lifetime=ipnsLifetime,
                    type=self.pyramidType,
                    description=description,
                    extra=extra)
                logUser.info('Multihash pyramid {pyr}: created'.format(
                    pyr=pyramidName))
            else:
                raise Exception('Could not generate IPNS key')
        except aioipfs.APIError as err:
            messageBox('IPFS error while creating pyramid: {}'.format(
                err.message))
        except Exception as err:
            messageBox('Error creating pyramid: {}'.format(str(err)))

    @ipfsOp
    async def injectQrcIcon(self, op, iconPath):
        _file = QFile(iconPath)
        if _file.exists():
            if not _file.open(QIODevice.ReadOnly):
                return False

            data = _file.readAll().data()
            entry = await op.addBytes(data, offline=True)
            if entry:
                self.iconCid = entry['Hash']
                return True


class AboutDialog(QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok, self)
        buttonBox.accepted.connect(self.accept)
        buttonBox.setCenterButtons(True)

        self.setWindowTitle('About')

        layout = QVBoxLayout()
        layout.addWidget(LabelWithURLOpener(text, parent=self))
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def accept(self):
        self.done(1)


class QSchemeCreateMappingDialog(QDialog):
    def __init__(self, mappedPath, title, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.mappedTo = mappedPath
        self.title = title

        self.ui = ui_qschemecreatemapping.Ui_QSchemeMappingDialog()
        self.ui.setupUi(self)
        self.ui.buttonBox.accepted.connect(self.accept)
        self.ui.buttonBox.rejected.connect(self.reject)
        self.ui.mappedPath.setText(
            '<b>{}</b>'.format(str(self.mappedTo)))

        regexp = QRegExp(r"[a-z0-9]+")
        self.ui.mappingName.setValidator(QRegExpValidator(regexp))

    def accept(self):
        ensure(self.addMapping())

    async def addMapping(self):
        name = self.ui.mappingName.text()
        if not name:
            return messageBox('Please provide a mapping name')

        if await database.hashmarkMappingAdd(
                name,
                self.title,
                str(self.mappedTo),
                ipnsresolvefreq=self.ui.ipnsResolveFrequency.value()):
            await self.app.towers['schemes'].qMappingsChanged.emit()

            self.done(1)
            messageBox(
                'You can now use the quick-access URL '
                '<b>q://{name}</b>'.format(name=name)
            )
        else:
            self.done(1)
            messageBox(
                'An error ocurred, check that a mapping does not '
                'already exist with that name')


class ResourceOpenConfirmDialog(QDialog):
    message = '''
    <p>IPFS object with path <b>{p}</b> (Content type: <b>{mtype}</b>)
    could not be opened.</p>

    <p>
    Open with system's default application ?
    </p>
    '''

    def __init__(self, rscPath, mType, secureEnv, parent=None):
        super().__init__(parent)

        self.rscPath = rscPath
        self.setWindowTitle('Open IPFS object')

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self
        )
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        buttonBox.setCenterButtons(True)

        layout = QVBoxLayout()

        label = QLabel(self.message.format(
            p=str(rscPath), mtype=mType.type))
        label.setMaximumWidth(600)
        label.setWordWrap(True)

        layout.addWidget(label)

        if not secureEnv:
            wLabel = QLabel(
                '<p style="color: red"> '
                'You are trying to open this object '
                'from an insecure context.'
                '</font>')
            layout.addWidget(wLabel)

        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def accept(self):
        self.done(1)


class TitleInputDialog(QDialog):
    def __init__(self, title, maxLength=64, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.title = title

        self.setWindowTitle(iTitle())

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self
        )
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        buttonBox.setCenterButtons(True)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(iTitle()))

        self.tEdit = QLineEdit(self)
        self.tEdit.setMaxLength(maxLength)
        self.tEdit.setText(title[0:maxLength - 1])

        layout.addWidget(self.tEdit)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def sizeHint(self):
        return QSize(
            self.app.desktopGeometry.width() / 2,
            100
        )

    def accept(self):
        self.done(1)


class GenericTextInputDialog(QDialog):
    def __init__(self, label, maxLength=64,
                 inputRegExp=r"[A-Za-z0-9/\-]+",
                 title=None, parent=None):
        super().__init__(parent)

        if title:
            self.setWindowTitle(title)

        self.app = QApplication.instance()
        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self
        )
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        buttonBox.setCenterButtons(True)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(label))

        self.tEdit = QLineEdit(self)
        self.tEdit.setMaxLength(maxLength)
        self.tEdit.setMaxLength(maxLength)

        self.tEdit.setValidator(
            QRegExpValidator(QRegExp(inputRegExp)))

        layout.addWidget(self.tEdit)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def enteredText(self):
        return self.tEdit.text()

    def sizeHint(self):
        return QSize(
            self.app.desktopGeometry.width() / 3,
            100
        )

    def accept(self):
        self.done(1)


class UneditableStringListModel(QStringListModel):
    def flags(self, index):
        return Qt.ItemFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)


class IPTagsSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()

        self.destTags = []

        self.allTagsModel = UneditableStringListModel(self)
        self.destTagsModel = UneditableStringListModel(self)
        self.allTagsProxyModel = QSortFilterProxyModel(self)
        self.allTagsProxyModel.setSourceModel(self.allTagsModel)

        self.ui = ui_iptagsmanager.Ui_IPTagsDialog()
        self.ui.setupUi(self)

        self.ui.destTagsView.setModel(self.destTagsModel)
        self.ui.destTagsView.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.ui.destTagsView.doubleClicked.connect(
            self.onTagDoubleClicked
        )

        self.ui.addTagButton.clicked.connect(lambda: ensure(self.addTag()))
        self.ui.lineEditTag.textChanged.connect(self.onTagEditChanged)
        self.ui.lineEditTag.setValidator(
            QRegExpValidator(QRegExp(r'[A-Za-z0-9-_@#]+')))
        self.ui.lineEditTag.setMaxLength(128)

        self.ui.tagItButton.clicked.connect(self.onTagObject)
        self.ui.untagItButton.clicked.connect(self.untagObject)
        self.ui.okButton.clicked.connect(lambda: ensure(self.validate()))
        self.ui.noTagsButton.clicked.connect(self.reject)

        self.setMinimumSize(
            self.app.desktopGeometry.width() / 2,
            (2 * self.app.desktopGeometry.height()) / 3
        )

    def onTagEditChanged(self, text):
        self.allTagsProxyModel.setFilterRegExp(text)
        self.ui.allTagsView.clearSelection()

    def onTagDoubleClicked(self, idx):
        ensure(self.tagObject([idx]))

    def onTagObject(self):
        ensure(self.tagObject())

    def untagObject(self):
        try:
            for idx in self.ui.destTagsView.selectedIndexes():
                tag = self.destTagsModel.data(
                    idx,
                    Qt.DisplayRole
                )

                if tag:
                    tagList = self.destTagsModel.stringList()
                    tagList.remove(tag)
                    self.destTagsModel.setStringList(tagList)
        except Exception:
            pass

    async def tagObject(self, indexes=None):
        if indexes is None:
            indexes = self.ui.allTagsView.selectedIndexes()

        for idx in indexes:
            tag = self.allTagsProxyModel.data(
                idx,
                Qt.DisplayRole
            )

            if tag and tag not in self.destTagsModel.stringList():
                self.destTagsModel.setStringList(
                    self.destTagsModel.stringList() + [tag]
                )

    async def initDialog(self):
        await self.updateAllTags()

    async def addTag(self):
        tagname = self.ui.lineEditTag.text()
        if not tagname:
            return

        await database.ipTagAdd(ipTagsFormat(tagname))
        self.ui.lineEditTag.clear()
        await self.updateAllTags()

    async def updateAllTags(self):
        tags = [t.name for t in await database.ipTagsAll()]
        self.allTagsModel.setStringList(tags)
        self.ui.allTagsView.setModel(self.allTagsProxyModel)
        self.allTagsProxyModel.sort(0)

    async def validate(self):
        self.destTags = self.destTagsModel.stringList()
        self.done(1)


class HashmarkIPTagsDialog(IPTagsSelectDialog):
    def __init__(
            self,
            hashmark,
            parent=None):
        super(HashmarkIPTagsDialog, self).__init__(parent)

        self.app = QApplication.instance()
        self.hashmark = hashmark
        self.setWindowTitle(iHashmarkIPTagsEdit())

        self.setMinimumSize(
            self.app.desktopGeometry.width() / 2,
            (2 * self.app.desktopGeometry.height()) / 3
        )

    async def initDialog(self):
        await self.hashmark._fetch_all()
        await self.updateAllTags()

    async def validate(self):
        hmTags = self.destTagsModel.stringList()
        await database.hashmarkTagsUpdate(self.hashmark, hmTags)
        self.done(1)


class DownloadOpenObjectDialog(QDialog):
    def __init__(self, ipfsPath, downItem, prechoice, parent=None):
        super().__init__(parent)

        self.setWindowTitle(iDownloadOpenDialog())
        self.app = QApplication.instance()
        self.downloadItem = downItem
        self.objectPath = ipfsPath

        self.choiceCombo = QComboBox(self)
        self.choiceCombo.addItem(iDownload())
        self.choiceCombo.addItem(iOpen())
        self.choiceCombo.currentIndexChanged.connect(self.onChoiceChange)

        if prechoice == 'open':
            self.choiceCombo.setCurrentIndex(1)

        label = QLabel(ipfsPath.ipfsUrl)
        label.setMaximumWidth(self.app.desktopGeometry.width() / 2)
        label.setWordWrap(True)
        label.setStyleSheet(boldLabelStyle())

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttonBox.setCenterButtons(True)

        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(self.choiceCombo)
        layout.addWidget(buttonBox)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        self.setLayout(layout)

    def onChoiceChange(self, idx):
        pass

    def choice(self):
        return self.choiceCombo.currentIndex()

    def accept(self):
        self.done(1)

    def reject(self):
        self.done(0)


class MFSImportOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = ui_mfsoptionsdialog.Ui_MFSImportOptionsDialog()
        self.ui.setupUi(self)
        self.ui.buttonBox.accepted.connect(self.accept)
        self.ui.buttonBox.rejected.connect(self.reject)

    def options(self):
        return {
            'hiddenFiles': self.ui.hiddenFiles.isChecked(),
            'useGitIgnore': self.ui.gitignore.isChecked(),
            'useFilestore': self.ui.filestore.isChecked(),
            'tsMetadata': self.ui.tsMetadata.isChecked(),
            'rawLeaves': self.ui.rawLeaves.isChecked(),
            'wrap': self.ui.wrap.isChecked()
        }

    def accept(self):
        self.done(1)

    def reject(self):
        self.done(0)
