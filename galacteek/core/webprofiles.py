from PyQt5.QtWidgets import QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineProfile
from PyQt5.QtWebEngineWidgets import QWebEngineSettings
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor

from galacteek import log

from galacteek.dweb.webscripts import ethereumClientScripts

from galacteek.core.schemes import SCHEME_DWEB
from galacteek.core.schemes import SCHEME_ENS
from galacteek.core.schemes import SCHEME_ENSR
from galacteek.core.schemes import SCHEME_FS
from galacteek.core.schemes import SCHEME_IPFS
from galacteek.core.schemes import SCHEME_IPNS
from galacteek.core.schemes import SCHEME_Q


WP_NAME_MINIMAL = 'minimal'
WP_NAME_IPFS = 'ipfs'
WP_NAME_WEB3 = 'web3'


webProfilesPrio = {
    WP_NAME_MINIMAL: 0,
    WP_NAME_IPFS: 1,
    WP_NAME_WEB3: 2
}


class IPFSRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()

        if url.isValid():
            log.debug('IPFS interceptor for URL: {}'.format(
                url.toString()))


class BaseProfile(QWebEngineProfile):
    def __init__(self, storageName='base', parent=None):
        super(BaseProfile, self).__init__(storageName, parent)

        self.app = QApplication.instance()
        self.webScripts = self.scripts()
        self.webSettings = self.settings()
        self.profileName = storageName
        self.installIpfsSchemeHandlers()
        self.installScripts()

        self.downloadRequested.connect(
            self.app.downloadsManager.onDownloadRequested)

    def installHandler(self, scheme, handler):
        sch = scheme if isinstance(scheme, bytes) else scheme.encode()
        self.installUrlSchemeHandler(sch, handler)

    def installScripts(self):
        pass

    def installIpfsSchemeHandlers(self):
        # XXX Remove fs: soon
        for scheme in [SCHEME_DWEB, SCHEME_FS]:
            self.installHandler(scheme, self.app.ipfsSchemeHandler)

        for scheme in [SCHEME_IPFS, SCHEME_IPNS]:
            self.installHandler(scheme, self.app.nativeIpfsSchemeHandler)

        self.installHandler(SCHEME_ENS, self.app.ensProxySchemeHandler)
        self.installHandler(SCHEME_ENSR, self.app.ensSchemeHandler)
        self.installHandler(SCHEME_Q, self.app.qSchemeHandler)


class MinimalProfile(BaseProfile):
    def __init__(self, storageName=WP_NAME_MINIMAL, parent=None):
        super(MinimalProfile, self).__init__(storageName, parent)


class IPFSProfile(BaseProfile):
    """
    IPFS web profile
    """

    def __init__(self, storageName=WP_NAME_IPFS, parent=None):
        super(IPFSProfile, self).__init__(storageName, parent)

        self.setSettings()

    def setSettings(self):
        self.webSettings.setAttribute(QWebEngineSettings.PluginsEnabled,
                                      True)
        self.webSettings.setAttribute(QWebEngineSettings.LocalStorageEnabled,
                                      True)

    def installScripts(self):
        exSc = self.webScripts.findScript('ipfs-http-client')
        if self.app.settingsMgr.jsIpfsApi is True and exSc.isNull():
            for script in self.app.scriptsIpfs:
                self.webScripts.insert(script)

    def installIpfsSchemeHandlersOld(self):
        # XXX Remove fs: soon
        for scheme in [SCHEME_DWEB, SCHEME_FS]:
            self.installUrlSchemeHandler(
                scheme.encode(), self.app.ipfsSchemeHandler)

        for scheme in [SCHEME_IPFS, SCHEME_IPNS]:
            self.installUrlSchemeHandler(
                scheme.encode(), self.app.nativeIpfsSchemeHandler)

        self.installUrlSchemeHandler(
            SCHEME_ENS.encode(), self.app.ensSchemeHandler)


class Web3Profile(IPFSProfile):
    """
    Web3 profile. Derives from the IPFS profile and
    adds an injection script to provide window.web3
    """

    def __init__(self, storageName=WP_NAME_WEB3, parent=None):
        super(Web3Profile, self).__init__(storageName, parent)

        self.installWeb3Scripts()

    def installWeb3Scripts(self):
        if self.app.settingsMgr.ethereumEnabled:
            ethereumScripts = ethereumClientScripts(
                self.app.getEthParams())
            if ethereumScripts:
                [self.webScripts.insert(script) for script in
                 ethereumScripts]
