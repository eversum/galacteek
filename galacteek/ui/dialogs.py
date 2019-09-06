import re
import aioipfs

from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtWidgets import QInputDialog
from PyQt5.QtWidgets import QToolButton
from PyQt5.QtWidgets import QDialogButtonBox
from PyQt5.QtWidgets import QLabel
from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QGridLayout
from PyQt5.QtWidgets import QFormLayout

from PyQt5.QtCore import QSize
from PyQt5.QtCore import QFile
from PyQt5.QtCore import QIODevice
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtCore import QRegExp
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QUrl

from PyQt5.QtGui import QClipboard
from PyQt5.QtGui import QPixmap
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QRegExpValidator

from galacteek import GALACTEEK_NAME
from galacteek import asyncify
from galacteek import ensure
from galacteek import logUser

from galacteek.core.ipfsmarks import *
from galacteek.core import countries
from galacteek.core.ipfsmarks import categoryValid
from galacteek.core.profile import UserInfos
from galacteek.ipfs import cidhelpers
from galacteek.ipfs.ipfsops import *
from galacteek.ipfs.wrappers import ipfsOp, ipfsOpFn

from . import ui_addhashmarkdialog
from . import ui_addfeeddialog
from . import ui_ipfscidinputdialog, ui_ipfsmultiplecidinputdialog
from . import ui_profileeditdialog
from . import ui_donatedialog
from . import ui_qschemecreatemapping

from .helpers import *
from .widgets import ImageWidget
from .widgets import HorizontalLine
from .widgets import IconSelector
from .widgets import LabelWithURLOpener

from .i18n import iDoNotPin
from .i18n import iPinSingle
from .i18n import iPinRecursive
from .i18n import iNoTitleProvided


def boldLabelStyle():
    return 'QLabel { font-weight: bold; }'


class AddHashmarkDialog(QDialog):
    def __init__(
            self,
            marks,
            resource,
            title,
            description,
            stats,
            pin=False,
            pinRecursive=False,
            parent=None):
        super().__init__(parent)

        self.ipfsResource = resource
        self.marks = marks
        self.stats = stats if stats else {}
        self.iconCid = None

        self.ui = ui_addhashmarkdialog.Ui_AddHashmarkDialog()
        self.ui.setupUi(self)
        self.ui.resourceLabel.setText(self.ipfsResource)
        self.ui.resourceLabel.setStyleSheet(boldLabelStyle())
        self.ui.resourceLabel.setToolTip(self.ipfsResource)
        self.ui.newCategory.textChanged.connect(self.onNewCatChanged)
        self.ui.title.setText(title)

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

        regexp1 = QRegExp(r"[A-Za-z0-9\/_-]+")  # noqa
        self.ui.newCategory.setValidator(QRegExpValidator(regexp1))
        self.ui.newCategory.setMaxLength(64)

        if pin is True:
            self.ui.pinCombo.setCurrentIndex(1)
        elif pinRecursive is True:
            self.ui.pinCombo.setCurrentIndex(2)

        if isinstance(description, str):
            self.ui.description.insertPlainText(description)

        for cat in self.marks.getCategories():
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
        else:
            category = self.ui.category.currentText()

        pSingle = (self.ui.pinCombo.currentIndex() == 1)
        pRecursive = (self.ui.pinCombo.currentIndex() == 2)

        mark = IPFSHashMark.make(
            self.ipfsResource,
            title=title,
            share=share,
            comment=self.ui.comment.text(),
            description=description,
            pinSingle=pSingle,
            pinRecursive=pRecursive,
            icon=self.iconCid,
            datasize=self.stats.get(
                'DataSize',
                None),
            cumulativesize=self.stats.get(
                'CumulativeSize',
                None),
            numlinks=self.stats.get(
                'NumLinks',
                None))

        self.marks.insertMark(mark, category)
        self.done(0)


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
        share = self.ui.share.isChecked()
        autoPin = self.ui.autoPin.isChecked()
        feedName = self.ui.feedName.text()

        if len(feedName) == 0:
            return messageBox('Please specify a feed name')

        self.marks.follow(self.ipfsResource, self.ui.feedName.text(),
                          resolveevery=self.ui.resolve.value(),
                          share=share, autoPin=autoPin)
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


def notEmpty(v):
    return v != ''


class ProfileEditDialog(QDialog):
    genderMapping = {
        'Unspecified': UserInfos.GENDER_UNSPECIFIED,
        'Male': UserInfos.GENDER_MALE,
        'Female': UserInfos.GENDER_FEMALE
    }

    def __init__(self, profile, parent=None):
        super().__init__(parent)

        self.profile = profile
        self.countryList = countries.countryList
        self.previousUsername = self.profile.userInfo.username

        self.ui = ui_profileeditdialog.Ui_ProfileEditDialog()
        self.ui.setupUi(self)
        self.ui.tabWidget.setCurrentIndex(0)

        self.loadCountryData()

        self.ui.labelWarning.setStyleSheet('QLabel { font-weight: bold; }')
        self.ui.username.setText(self.profile.userInfo.username)
        self.ui.firstname.setText(self.profile.userInfo.firstname)
        self.ui.lastname.setText(self.profile.userInfo.lastname)
        self.ui.email.setText(self.profile.userInfo.email)
        self.ui.org.setText(self.profile.userInfo.org)
        self.ui.city.setText(self.profile.userInfo.city)
        self.ui.bio.setText(self.profile.userInfo.bio)

        for gender, gvalue in self.genderMapping.items():
            self.ui.gender.addItem(gender)
            if self.profile.userInfo.gender == gvalue:
                self.ui.gender.setCurrentText(gender)

        if notEmpty(self.profile.userInfo.countryName):
            self.ui.countryBox.setCurrentText(
                self.profile.userInfo.countryName)
        else:
            self.ui.countryBox.setCurrentText('Unspecified')

        if notEmpty(self.profile.userInfo.avatarCid):
            self.updateAvatarCid()

        self.ui.profileCryptoId.setText('<b>{0}</b>'.format(
            self.profile.userInfo.objHash))

        self.ui.changeIconButton.clicked.connect(self.changeIcon)
        self.ui.updateButton.clicked.connect(self.save)
        self.ui.cancelButton.clicked.connect(self.close)

        self.reloadIcon()

    def updateAvatarCid(self):
        self.ui.iconHash.setText('<a href="ipfs:{0}">{1}</a>'.format(
            cidhelpers.joinIpfs(self.profile.userInfo.avatarCid),
            self.profile.userInfo.avatarCid))

    def reloadIcon(self):
        ensure(self.loadIcon())

    def getCountryCode(self, name):
        for entry in self.countryList:
            if entry['name'] == name:
                return entry['code']

    def loadCountryData(self):
        for entry in self.countryList:
            self.ui.countryBox.addItem(entry['name'])

        self.ui.countryBox.addItem('Unspecified')

    @asyncify
    async def loadIcon(self):
        @ipfsOpFn
        async def load(op, cid):
            try:
                imgData = await op.client.cat(cid)
                img1 = QImage()
                img1.loadFromData(imgData)
                img = img1.scaledToWidth(256)
                self.ui.iconPixmap.setPixmap(QPixmap.fromImage(img))
            except Exception:
                messageBox('Error while loading image')

        if self.profile.userInfo.avatarCid != '':
            await load(self.profile.userInfo.avatarCid)

    def changeIcon(self):
        fps = filesSelectImages()
        if len(fps) > 0:
            ensure(self.setIcon(fps.pop()))

    @ipfsOp
    async def setIcon(self, op, fp):
        entry = await op.addPath(fp, recursive=False)
        if entry:
            self.profile.userInfo.setAvatarCid(entry['Hash'])
            self.reloadIcon()
            self.updateAvatarCid()

    def save(self):
        kw = {}
        for key in ['username', 'firstname',
                    'lastname', 'email', 'org',
                    'city']:
            val = getattr(self.ui, key).text()
            ma = re.search(r"[a-zA-Z\_\-\@\.\+\'\´0-9\s]*", val)
            if ma:
                kw[key] = val

        try:
            kw['bio'] = self.ui.bio.toPlainText()
        except:
            pass

        country = self.ui.countryBox.currentText()
        code = self.getCountryCode(country)

        if country and code:
            self.profile.userInfo.setCountryInfo(country, code)

        genderSelected = self.ui.gender.currentText()
        for gender, gvalue in self.genderMapping.items():
            if genderSelected == gender:
                kw['gender'] = gvalue

        self.profile.userInfo.setInfos(**kw)

        if self.previousUsername != self.profile.userInfo.username:
            self.profile.userInfo.usernameChanged.emit()

        self.profile.userInfo.changed.emit()
        self.done(1)

    def reject(self):
        self.done(0)


class ChooseProgramDialog(QInputDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle('Choose a program')
        self.setInputMode(QInputDialog.TextInput)
        self.setLabelText(
            '''Command arguments (example: <b>mupdf %f</b>).
                <b>%f</b> is replaced with the file path''')


class AddAtomFeedDialog(QInputDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle('Add an Atom feed')
        self.setInputMode(QInputDialog.TextInput)
        self.setLabelText('Atom feed URL')

    def sizeHint(self):
        return QSize(600, 140)


class AddMultihashPyramidDialog(QDialog):
    def __init__(self, marks, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()

        self.marks = marks
        self.iconCid = None
        self.customCategory = None

        cat = QLabel('Category')
        self.categoryCombo = QComboBox(self)
        cat.setBuddy(self.categoryCombo)

        for category in marks.getCategories():
            self.categoryCombo.addItem(category)

        label = QLabel('Pyramid name')
        restrictRegexp = QRegExp("[0-9A-Za-z-_]+")  # noqa
        restrictRegexp2 = QRegExp("[0-9A-Za-z-_/]+")  # noqa

        self.nameLine = QLineEdit()
        self.nameLine.setMaxLength(32)
        self.nameLine.setValidator(QRegExpValidator(restrictRegexp))
        label.setBuddy(self.nameLine)

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)

        catLayout = QHBoxLayout()
        catLayout.addWidget(cat)
        catLayout.addWidget(self.categoryCombo)

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
        pickIconLayout.addWidget(QLabel('Choose icon'))
        pickIconLayout.addWidget(self.iconSelector)

        mainLayout = QGridLayout()
        mainLayout.addLayout(nameLayout, 0, 0)
        mainLayout.addLayout(descrLayout, 1, 0)
        mainLayout.addWidget(HorizontalLine(self), 2, 0)
        mainLayout.addLayout(catLayout, 3, 0)
        mainLayout.addLayout(catCustomLayout, 4, 0)
        mainLayout.addWidget(HorizontalLine(self), 5, 0)
        mainLayout.addLayout(ipnsLTimeLayout, 6, 0)
        mainLayout.addLayout(pickIconLayout, 7, 0)
        mainLayout.addWidget(buttonBox, 8, 0)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        self.setLayout(mainLayout)

        self.nameLine.setFocus(Qt.OtherFocusReason)

    def onIconSelected(self, iconCid):
        self.iconCid = iconCid

    def onCustomCategory(self, text):
        self.categoryCombo.setEnabled(len(text) == 0)
        self.customCategory = text

    def reject(self):
        self.done(0)

    def accept(self):
        pyramidName = self.nameLine.text()
        descr = self.descrLine.text()
        lifetime = self.lifetimeCombo.currentText()

        if len(pyramidName) == 0 or len(descr) == 0:
            return messageBox('Please give a name and description')

        if isinstance(self.customCategory, str) and \
                categoryValid(self.customCategory):
            category = self.customCategory
        else:
            category = self.categoryCombo.currentText()

        ipnsKeyName = 'galacteek.pyramids.{cat}.{name}'.format(
            cat=category.replace('/', '_'), name=pyramidName)

        self.done(1)

        ensure(self.createPyramid(pyramidName, category, ipnsKeyName,
                                  descr, lifetime))

    @ipfsOp
    async def createPyramid(self, ipfsop, pyramidName, category, ipnsKeyName,
                            description, ipnsLifetime):
        try:
            logUser.info(
                'Multihash pyramid {pyr}: generating IPNS key ...'.format(
                    pyr=pyramidName))
            ipnsKey = await ipfsop.keyGen(ipnsKeyName)
        except aioipfs.APIError:
            return
        else:
            if ipnsKey:
                self.marks.pyramidNew(
                    pyramidName, category, self.iconCid,
                    ipnskey=ipnsKey['Id'],
                    lifetime=ipnsLifetime,
                    description=description)
                logUser.info('Multihash pyramid {pyr}: created'.format(
                    pyr=pyramidName))

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

        self.setWindowTitle('About')

        layout = QVBoxLayout()
        layout.addWidget(LabelWithURLOpener(text, parent=self))
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def accept(self):
        self.done(1)


class QSchemeCreateMappingDialog(QDialog):
    def __init__(self, mappedPath, parent=None):
        super().__init__(parent)

        self.app = QApplication.instance()
        self.mappedTo = mappedPath

        self.ui = ui_qschemecreatemapping.Ui_QSchemeMappingDialog()
        self.ui.setupUi(self)
        self.ui.buttonBox.accepted.connect(self.accept)
        self.ui.buttonBox.rejected.connect(self.reject)
        self.ui.mappedPath.setText(
            '<b>{}</b>'.format(str(self.mappedTo)))

        regexp = QRegExp(r"[a-z0-9]+")
        self.ui.mappingName.setValidator(QRegExpValidator(regexp))

    def accept(self):
        name = self.ui.mappingName.text()
        if not name:
            return messageBox('Please provide a mapping name')

        if self.app.marksLocal.qaMap(
                name,
                self.mappedTo,
                ipnsResolveFrequency=self.ui.ipnsResolveFrequency.value()):
            self.app.towers['schemes'].qMappingsChanged.emit()
            self.done(1)
            messageBox(
                'You can now use the quick-access URL '
                '<b>q://{name}</b>'.format(name=name),
                richText=True
            )
        else:
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
        self.setWindowTitle('Open resource')

        buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self
        )
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        layout = QVBoxLayout()

        label = QLabel(self.message.format(
            p=str(rscPath), mtype=mType.type))
        label.setMaximumWidth(600)
        label.setWordWrap(True)

        layout.addWidget(label)

        okButton = buttonBox.button(QDialogButtonBox.Ok)

        if not secureEnv:
            okButton.setEnabled(False)
            ignButton = QToolButton(self)
            ignButton.setCheckable(True)
            ignButton.setText('Let me open it anyway')
            ignButton.toggled.connect(
                lambda state: okButton.setEnabled(state))

            wLabel = QLabel(
                '<p style="color: red"> '
                'You are trying to open this object '
                'from an insecure environment.'
                '</font>')
            layout.addWidget(wLabel)
            layout.addWidget(ignButton)

        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def accept(self):
        self.done(1)
