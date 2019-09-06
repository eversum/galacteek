from PyQt5.QtCore import QSettings

# Settings sections
CFG_SECTION_IPFSD = 'ipfsdaemon'
CFG_SECTION_IPFS = 'ipfs'
CFG_SECTION_BROWSER = 'browser'
CFG_SECTION_IPFSCONN1 = 'ipfsconn1'
CFG_SECTION_UI = 'ui'
CFG_SECTION_HISTORY = 'history'
CFG_SECTION_USERINFO = 'userinfo'
CFG_SECTION_ETHEREUM = 'ethereum'
CFG_SECTION_ORBITDB = 'orbitdb'

CFG_KEY_ENABLED = 'enabled'

# These keys are for ipfsdaemon and ipfsconn sections
CFG_KEY_APIPORT = 'apiport'
CFG_KEY_SWARMPORT = 'swarmport'
CFG_KEY_HTTPGWPORT = 'httpgwport'
CFG_KEY_HTTPGWWRITABLE = 'httpgwwritable'
CFG_KEY_NAMESYS_PUBSUB = 'namesyspubsub'
CFG_KEY_PUBSUB_ROUTER = 'pubsub_router'
CFG_KEY_HOST = 'host'
CFG_KEY_SWARMLOWWATER = 'swarm_lowwater'
CFG_KEY_SWARMHIGHWATER = 'swarm_highwater'
CFG_KEY_STORAGEMAX = 'storagemax'  # integer, max storage in Gb
CFG_KEY_CORS = 'cors'
CFG_KEY_ROUTINGMODE = 'routingmode'
CFG_KEY_NICE = 'nice'

# Browser
CFG_KEY_HOMEURL = 'homeurl'
CFG_KEY_GOTOHOME = 'gotohomeonnewtab'
CFG_KEY_DLPATH = 'downloadspath'
CFG_KEY_ALLOWHTTPBROWSING = 'httpbrowsing'
CFG_KEY_JSAPI = 'jsapi'
CFG_KEY_PPAPIPLUGINS = 'ppapiplugins'
CFG_KEY_DEFAULTWEBPROFILE = 'defaultwebprofile'

# History
CFG_KEY_HISTORYENABLED = 'enabled'
CFG_KEY_TIMEOUTURLEDIT = 'timeouturledit'

# IPFS
CFG_KEY_PUBSUB = 'pubsub'
CFG_KEY_HASHMARKSEXCH = 'hashmarksexch'

# UI
CFG_KEY_WRAPSINGLEFILES = 'wrapsinglefiles'
CFG_KEY_WRAPDIRECTORIES = 'wrapdirectories'
CFG_KEY_HIDEHASHES = 'hidehashes'
CFG_KEY_LANG = 'lang'
CFG_KEY_BROWSER_AUTOPIN = 'browserautopin'

CFG_KEY_MAINWINDOW_STATE = 'mainwindow_area'
CFG_KEY_MAINWINDOW_GEOMETRY = 'mainwindow_geometry'

# OrbitDB
CFG_KEY_CONNECTOR_LISTENPORT = 'connectorlistenport'

# Ethereum
CFG_KEY_PROVIDERTYPE = 'providertype'
CFG_KEY_RPCURL = 'rpcurl'

# for fast access
S_HOMEURL = (CFG_SECTION_BROWSER, CFG_KEY_HOMEURL)
S_GOTOHOME = (CFG_SECTION_BROWSER, CFG_KEY_GOTOHOME)
S_DOWNLOADS_PATH = (CFG_SECTION_BROWSER, CFG_KEY_DLPATH)

# Default homepage
HOME_DEFAULT = \
    'ipfs://bafybeiemxf5abjwjbikoz4mc3a3dla6ual3jsgpdr4cjr3oz3evfyavhwq/wiki/'

ROUTER_TYPE_FLOOD = 'floodsub'
ROUTER_TYPE_GOSSIP = 'gossipsub'


def setDefaultSettings(gApp):
    # Sets the default settings
    sManager = gApp.settingsMgr

    section = CFG_SECTION_IPFSD
    sManager.setDefaultSetting(section, CFG_KEY_APIPORT, 5001)
    sManager.setDefaultSetting(section, CFG_KEY_SWARMPORT, 4001)
    sManager.setDefaultSetting(section, CFG_KEY_HTTPGWPORT, 8080)
    sManager.setDefaultSetting(section, CFG_KEY_SWARMHIGHWATER, 900)
    sManager.setDefaultSetting(section, CFG_KEY_SWARMLOWWATER, 600)
    sManager.setDefaultSetting(section, CFG_KEY_STORAGEMAX, 50)
    sManager.setDefaultSetting(section, CFG_KEY_ROUTINGMODE, 'dht')
    sManager.setDefaultSetting(section, CFG_KEY_PUBSUB_ROUTER,
                               ROUTER_TYPE_FLOOD)
    sManager.setDefaultSetting(section, CFG_KEY_NICE, 20)
    sManager.setDefaultTrue(section, CFG_KEY_CORS)
    sManager.setDefaultTrue(section, CFG_KEY_ENABLED)
    sManager.setDefaultFalse(section, CFG_KEY_NAMESYS_PUBSUB)
    sManager.setDefaultFalse(section, CFG_KEY_HTTPGWWRITABLE)

    section = CFG_SECTION_BROWSER
    sManager.setDefaultSetting(section, CFG_KEY_HOMEURL, HOME_DEFAULT)
    sManager.setDefaultSetting(section, CFG_KEY_DLPATH,
                               gApp.defaultDownloadsLocation)
    sManager.setDefaultSetting(section, CFG_KEY_DEFAULTWEBPROFILE,
                               'minimal')
    sManager.setDefaultTrue(section, CFG_KEY_GOTOHOME)
    sManager.setDefaultTrue(section, CFG_KEY_JSAPI)
    sManager.setDefaultTrue(section, CFG_KEY_ALLOWHTTPBROWSING)
    sManager.setDefaultTrue(section, CFG_KEY_PPAPIPLUGINS)

    # Default IPFS connection when not spawning daemon
    section = CFG_SECTION_IPFSCONN1
    sManager.setDefaultSetting(section, CFG_KEY_HOST, 'localhost')
    sManager.setDefaultSetting(section, CFG_KEY_APIPORT, 5001)
    sManager.setDefaultSetting(section, CFG_KEY_HTTPGWPORT, 8080)

    section = CFG_SECTION_IPFS
    sManager.setDefaultTrue(section, CFG_KEY_PUBSUB)
    sManager.setDefaultTrue(section, CFG_KEY_HASHMARKSEXCH)

    section = CFG_SECTION_UI
    sManager.setDefaultTrue(section, CFG_KEY_WRAPSINGLEFILES)
    sManager.setDefaultFalse(section, CFG_KEY_WRAPDIRECTORIES)
    sManager.setDefaultFalse(section, CFG_KEY_HIDEHASHES)
    sManager.setDefaultSetting(section, CFG_KEY_LANG, 'en')
    sManager.setDefaultFalse(section, CFG_KEY_BROWSER_AUTOPIN)

    section = CFG_SECTION_HISTORY
    sManager.setDefaultFalse(section, CFG_KEY_HISTORYENABLED)
    sManager.setDefaultSetting(section, CFG_KEY_TIMEOUTURLEDIT, 1600)

    section = CFG_SECTION_ORBITDB
    sManager.setDefaultSetting(section, CFG_KEY_CONNECTOR_LISTENPORT, 3000)

    section = CFG_SECTION_ETHEREUM
    sManager.setDefaultFalse(section, CFG_KEY_ENABLED)
    sManager.setDefaultSetting(section, CFG_KEY_PROVIDERTYPE, 'http')
    sManager.setDefaultSetting(section, CFG_KEY_RPCURL,
                               'http://localhost:7545')

    sManager.sync()
    return True


class SettingsManager(object):
    # QSettings has its problems with pyqt5 regarding booleans
    trueVal = 'true'
    falseVal = 'false'

    def __init__(self, path=None):
        self.settings = QSettings(path, QSettings.IniFormat)

    def sync(self):
        """ Synchronize settings to disk """
        return self.settings.sync()

    def eSet(self, key, value):
        """ Easy set. key is a (section, key) tuple """
        return self.setSetting(key[0], key[1], value)

    def eGet(self, key, type=None):
        """ Easy get. key is a (section, key) tuple """
        return self.getSetting(key[0], key[1], type=type)

    def setSetting(self, section, name, value):
        """ Changes a setting to given value

        :param str section: setting section
        :param str name: key inside the section
        :param value: setting value
        """
        self.settings.setValue('{0}/{1}'.format(section, name), value)

    def setDefaultSetting(self, section, name, value):
        """
        Sets default setting for section and name if that setting hasn't
        been registered yet
        """
        existing = self.getSetting(section, name)
        if not existing:
            self.settings.setValue('{0}/{1}'.format(section, name), value)

    def setDefaultTrue(self, section, name):
        return self.setDefaultSetting(section, name, self.trueVal)

    def setDefaultFalse(self, section, name):
        return self.setDefaultSetting(section, name, self.falseVal)

    def getInt(self, section, name):
        """
        Gets the setting referenced by section and name, casting it as
        an integer
        """
        return self.getSetting(section, name, type=int)

    def getSetting(self, section, name, type=None):
        """ Gets a setting, casting it to the given type

        :param str section: setting section
        :param str name: key inside the section
        :param type: type to convert to
        """
        key = '{0}/{1}'.format(section, name)
        if type:
            return self.settings.value(key, type=type)
        else:
            return self.settings.value(key)

    def setTrue(self, section, name):
        return self.setSetting(section, name, self.trueVal)

    def setFalse(self, section, name):
        return self.setSetting(section, name, self.falseVal)

    def setBoolFrom(self, section, name, boolVal):
        if boolVal is True:
            self.setTrue(section, name)
        elif boolVal is False:
            self.setFalse(section, name)

    def isTrue(self, section, name):
        return self.getSetting(section, name) == self.trueVal

    def isFalse(self, section, name):
        return self.getSetting(section, name) == self.falseVal

    # Properties

    @property
    def hideHashes(self):
        return self.isTrue(CFG_SECTION_UI, CFG_KEY_HIDEHASHES)

    @property
    def wrapFiles(self):
        return self.isTrue(CFG_SECTION_UI, CFG_KEY_WRAPSINGLEFILES)

    @property
    def wrapDirectories(self):
        return self.isTrue(CFG_SECTION_UI, CFG_KEY_WRAPDIRECTORIES)

    @property
    def allowHttpBrowsing(self):
        return self.isTrue(CFG_SECTION_BROWSER, CFG_KEY_ALLOWHTTPBROWSING)

    @property
    def jsIpfsApi(self):
        return self.isTrue(CFG_SECTION_BROWSER, CFG_KEY_JSAPI)

    @property
    def ppApiPlugins(self):
        return self.isTrue(CFG_SECTION_BROWSER, CFG_KEY_PPAPIPLUGINS)

    @property
    def mainWindowGeometry(self):
        return self.getSetting(CFG_SECTION_UI, CFG_KEY_MAINWINDOW_GEOMETRY)

    @property
    def mainWindowState(self):
        return self.getSetting(CFG_SECTION_UI, CFG_KEY_MAINWINDOW_STATE)

    @property
    def browserAutoPin(self):
        return self.isTrue(CFG_SECTION_UI, CFG_KEY_BROWSER_AUTOPIN)

    @property
    def downloadsDir(self):
        return self.getSetting(CFG_SECTION_BROWSER, CFG_KEY_DLPATH)

    @property
    def urlHistoryEnabled(self):
        return self.isTrue(CFG_SECTION_HISTORY, CFG_KEY_HISTORYENABLED)

    @property
    def urlHistoryEditTimeout(self):
        return self.getInt(CFG_SECTION_HISTORY, CFG_KEY_TIMEOUTURLEDIT)

    @property
    def ethereumEnabled(self):
        return self.isTrue(CFG_SECTION_ETHEREUM, CFG_KEY_ENABLED)

    @property
    def ethereumProvType(self):
        return self.isTrue(CFG_SECTION_ETHEREUM, CFG_KEY_PROVIDERTYPE)

    @property
    def ethereumRpcUrl(self):
        return self.isTrue(CFG_SECTION_ETHEREUM, CFG_KEY_RPCURL)

    @property
    def defaultWebProfile(self):
        return self.getSetting(CFG_SECTION_BROWSER, CFG_KEY_DEFAULTWEBPROFILE)
