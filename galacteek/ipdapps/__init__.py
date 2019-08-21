import pkg_resources
import importlib
import os.path
import os
import jinja2

from PyQt5.QtCore import QTimer

from galacteek import log
from galacteek.core.objects import GObject
from galacteek.core.objects import pyqtSignal
from galacteek.core import runningApp
from galacteek.dweb import render
from galacteek.ipfs import ipfsOp
from galacteek.core.fswatcher import FileWatcher

dappsPkg = __name__


def availableDapps():
    _dapps = {}
    try:
        listing = pkg_resources.resource_listdir(dappsPkg, '')
        for fn in listing:
            path = pkg_resources.resource_filename(dappsPkg, fn)
            if not fn.startswith('_') and os.path.isdir(path):
                _dapps[fn] = path
        return _dapps
    except Exception:
        pass


def dappGetModule(dappName):
    modname = '{0}.{1}'.format(dappsPkg, dappName)

    try:
        module = importlib.import_module(modname)
    except Exception as err:
        print(str(err))
        return None
    else:
        return module


def dappsRegisterSchemes():
    # Called early (register dapps schemes before app creation)
    dapps = availableDapps()
    for dappName in dapps:
        mod = dappGetModule(dappName)
        if mod:
            print(dappName, mod, 'reg schemes')
            mod.declareUrlSchemes()


class IPLiveDapp(GObject):
    """
    Inter-Planetary Dapp
    """

    pkgContentsChanged = pyqtSignal(str)

    def __init__(self, ethCtrl, name, pkgPath,
                 offline=False, **kwargs):
        parent = kwargs.pop('parent', None)
        planet = kwargs.pop('planet', 'earth')
        initmod = kwargs.pop('initModule', None)

        super(IPLiveDapp, self).__init__(parent)

        self.app = runningApp()

        self._ethController = ethCtrl
        self._name = name
        self._pkgPath = pkgPath
        self._templatesPath = os.path.join(self._pkgPath, 'templates')
        self._assetsPath = os.path.join(self._pkgPath, 'assets')
        self._assetsCid = None
        self._args = kwargs
        self._planet = planet
        self._offline = offline

        self._ctx_params = {}

        self.jEnv = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self._templatesPath),
            enable_async=True
        )

        self._moduleInit = initmod
        self._watcher = FileWatcher()
        self._watchT = QTimer(self)
        self._watchT.timeout.connect(
            lambda: self.pkgContentsChanged.emit(self.name))

        self.watch(self._pkgPath)
        self._watcher.pathChanged.connect(self.onFileWatchChange)

    @property
    def name(self):
        return self._name

    @property
    def offline(self):
        # DAGs and assets in 'offline' mode (dev)
        return self._offline

    @property
    def planet(self):
        return self._planet

    @property
    def eth(self):
        return self._ethController

    @property
    def web3(self):
        return self.eth.web3

    @property
    def args(self):
        return self._args

    @property
    def assetsCid(self):
        return self._assetsCid

    async def registerSchemeHandlers(self):
        pass

    def watch(self, _dir):
        for root, dirs, files in os.walk(_dir):
            for d in dirs:
                if d.startswith('__'):
                    continue
                fp = os.path.join(root, d)
                self._watcher.watch(fp)
        self._watcher.watch(_dir)

    def compileTemplates(self):
        try:
            self.jEnv.compile_templates(self._templatesCompiledPath, zip=None)
        except Exception as err:
            print('Templates recompile error', str(err))

    @ipfsOp
    async def init(self, ipfsop):
        self.compileTemplates()
        await self.importAssets()

    def stop(self):
        pass

    @ipfsOp
    async def importAssets(self, ipfsop):
        if os.path.isdir(self._assetsPath):
            self._assetsCid = await ipfsop.addPath(
                self._assetsPath, recursive=True,
                offline=self.offline
            )

    async def renderTemplate(self, template, **kw):
        coro = render.ipfsRender
        kw.update(self._ctx_params)
        kw['offline'] = self.offline

        return await coro(self.jEnv,
                          template,
                          **kw
                          )

    async def renderTemplateWLink(self, dag, tmpl, **kw):
        # Render and link in the dag
        result = await self.renderTemplate(tmpl, **kw)
        return dag.mkLink(result)

    def onFileWatchChange(self, path):
        self._watchT.stop()
        self._watchT.start(3000)

    def reimportModule(self):
        self._watchT.stop()
        if self._moduleInit:
            try:
                importlib.reload(self._moduleInit)
            except ImportError:
                log.debug('Error reimporting module {}'.format(
                    self._moduleInit))

    async def dappReload(self):
        self._watchT.stop()
        log.debug('Dapp reload')

        await self.importAssets()
        try:
            self.jEnv.compile_templates(self._templatesCompiledPath)
        except Exception as err:
            print('Templates recompile error', str(err))
