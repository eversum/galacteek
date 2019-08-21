import re
import uuid
import aioipfs
import functools
import asyncio

from PyQt5.QtWebEngineCore import QWebEngineUrlSchemeHandler
from PyQt5.QtWebEngineCore import QWebEngineUrlScheme
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestJob

from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QIODevice
from PyQt5.QtCore import QBuffer
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QMutex

from galacteek import log
from galacteek import logUser
from galacteek import ensure
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.mimetype import detectMimeTypeFromBuffer
from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import ipfsRegSearchCid32
from galacteek.ipfs.ipfsops import APIErrorDecoder
from galacteek.dweb.render import renderTemplate
from galacteek.dweb.enswhois import ensContentHash

from galacteek.ipdapps import dappsRegisterSchemes


from yarl import URL


SCHEME_DWEB = 'dweb'
SCHEME_FS = 'fs'
SCHEME_IPFS = 'ipfs'
SCHEME_ENS = 'ens'
SCHEME_IPNS = 'ipns'
SCHEME_GALACTEEK = 'glk'
SCHEME_PALACE = 'palace'
SCHEME_MANUAL = 'manual'


# Default flags used by declareUrlScheme()
defaultSchemeFlags = QWebEngineUrlScheme.SecureScheme | \
    QWebEngineUrlScheme.ViewSourceAllowed

# Registered URL schemes
urlSchemes = {}


def allUrlSchemes():
    global urlSchemes
    return urlSchemes


def isSchemeRegistered(scheme):
    global urlSchemes
    for section, schemes in urlSchemes.items():
        if scheme in schemes:
            return True


def declareUrlScheme(name,
                     flags=defaultSchemeFlags,
                     syntax=QWebEngineUrlScheme.Syntax.Host,
                     defaultPort=QWebEngineUrlScheme.PortUnspecified,
                     schemeSection='core'):
    global urlSchemes
    scheme = QWebEngineUrlScheme(name.encode())
    scheme.setFlags(flags)
    scheme.setSyntax(syntax)
    scheme.setDefaultPort(defaultPort)
    QWebEngineUrlScheme.registerScheme(scheme)
    urlSchemes.setdefault(schemeSection, {})
    urlSchemes[schemeSection][name] = scheme
    return scheme


def registerMiscSchemes():
    declareUrlScheme(SCHEME_MANUAL,
                     syntax=QWebEngineUrlScheme.Syntax.Path,
                     schemeSection='misc'
                     )


def initializeSchemes():
    name = QWebEngineUrlScheme.schemeByName(SCHEME_DWEB.encode()).name()
    if name:
        # initializeSchemes() already called ?
        log.debug('initializeSchemes() already called')
        return

    declareUrlScheme(
        SCHEME_DWEB,
        syntax=QWebEngineUrlScheme.Syntax.Path,
    )

    declareUrlScheme(
        SCHEME_FS,
        syntax=QWebEngineUrlScheme.Syntax.Path,
    )

    declareUrlScheme(
        SCHEME_IPFS,
        syntax=QWebEngineUrlScheme.Syntax.Host
    )

    declareUrlScheme(
        SCHEME_IPNS,
        syntax=QWebEngineUrlScheme.Syntax.Host
    )

    declareUrlScheme(
        SCHEME_ENS,
        syntax=QWebEngineUrlScheme.Syntax.Host
    )

    dappsRegisterSchemes()
    registerMiscSchemes()


def initializeSchemesOld():
    name = QWebEngineUrlScheme.schemeByName(SCHEME_DWEB.encode()).name()
    if name:
        # initializeSchemes() already called ?
        return

    schemeDweb = QWebEngineUrlScheme(SCHEME_DWEB.encode())
    schemeDweb.setFlags(
        QWebEngineUrlScheme.SecureScheme |
        QWebEngineUrlScheme.ViewSourceAllowed
    )

    schemeFs = QWebEngineUrlScheme(SCHEME_FS.encode())
    schemeFs.setFlags(QWebEngineUrlScheme.SecureScheme)

    schemeIpfs = QWebEngineUrlScheme(SCHEME_IPFS.encode())
    schemeIpfs.setFlags(
        QWebEngineUrlScheme.SecureScheme |
        QWebEngineUrlScheme.ViewSourceAllowed
    )
    schemeIpfs.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    schemeIpfs.setDefaultPort(QWebEngineUrlScheme.PortUnspecified)

    schemeIpns = QWebEngineUrlScheme(SCHEME_IPNS.encode())
    schemeIpns.setFlags(
        QWebEngineUrlScheme.SecureScheme |
        QWebEngineUrlScheme.ViewSourceAllowed
    )
    schemeIpns.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    schemeIpns.setDefaultPort(QWebEngineUrlScheme.PortUnspecified)

    schemeEns = QWebEngineUrlScheme(SCHEME_ENS.encode())
    schemeEns.setFlags(QWebEngineUrlScheme.SecureScheme)

    QWebEngineUrlScheme.registerScheme(schemeDweb)
    QWebEngineUrlScheme.registerScheme(schemeFs)
    QWebEngineUrlScheme.registerScheme(schemeIpfs)
    QWebEngineUrlScheme.registerScheme(schemeEns)
    QWebEngineUrlScheme.registerScheme(schemeIpns)

    dappsRegisterSchemes()
    registerMiscSchemes()


def isIpfsUrl(url):
    if url.isValid():
        return url.scheme() in [SCHEME_FS, SCHEME_DWEB,
                                SCHEME_IPFS, SCHEME_IPNS]


def isNativeIpfsUrl(url):
    if url.isValid():
        return url.scheme() in [SCHEME_IPFS, SCHEME_IPNS]


class BaseURLSchemeHandler(QWebEngineUrlSchemeHandler):
    webProfileNeeded = None

    def reqFailed(self, request):
        return request.fail(QWebEngineUrlRequestJob.RequestFailed)

    def urlInvalid(self, request):
        return request.fail(QWebEngineUrlRequestJob.UrlInvalid)

    def urlNotFound(self, request):
        return request.fail(QWebEngineUrlRequestJob.UrlNotFound)

    def aborted(self, request):
        return request.fail(QWebEngineUrlRequestJob.RequestAborted)


class ENSWhoisSchemeHandler(BaseURLSchemeHandler):
    contentReady = pyqtSignal(str, QWebEngineUrlRequestJob, str, bytes)
    domainResolved = pyqtSignal(str, IPFSPath)

    def __init__(self, app, parent=None):
        super(ENSWhoisSchemeHandler, self).__init__(parent)

        self.app = app
        self.requests = {}

    def onRequestDestroyed(self, uid):
        if uid in self.requests:
            del self.requests[uid]

    async def handleRequest(self, request):
        rUrl = request.requestUrl()
        if not rUrl.isValid():
            return self.urlInvalid(request)

        domain = rUrl.host()
        uPath = rUrl.path()

        if not domain or len(domain) > 512:
            logUser.info('ENS: invalid domain request')
            return self.urlInvalid(request)

        logUser.info('ENS: resolving {0}'.format(domain))

        path = await ensContentHash(domain, sslverify=self.app.sslverify)
        if path and path.valid:
            self.domainResolved.emit(domain, path)
            sPath = path.child(uPath) if uPath else path
            logUser.info('ENS: {domain} resolved to {res}'.format(
                domain=domain, res=sPath.dwebUrl))
            return request.redirect(QUrl(sPath.dwebUrl))
        else:
            logUser.info('ENS: {domain} resolve failed'.format(
                domain=domain))
            request.fail(QWebEngineUrlRequestJob.UrlInvalid)

    def requestStarted(self, request):
        uid = str(uuid.uuid4())
        self.requests[uid] = request
        request.destroyed.connect(lambda: self.onRequestDestroyed(uid))
        ensure(self.handleRequest(self.requests[uid]))


class NativeIPFSSchemeHandler(BaseURLSchemeHandler):
    """
    Native scheme handler for URLs using the ipfs://<cidv1base32>
    or ipns://<fqdn>/.. formats

    We don't use the gateway at all here, making the async requests
    manually on the daemon.

    The requestStarted() function will first assign a UUID to the
    request and store the request in the handler so that it doesn't get
    garbage-collected by QtWebEngine. The handleRequest() coroutine
    is responsible for fetching the objects from IPFS. When the data
    is ready it will call the renderData() coroutine which will detect
    the MIME type, and emit the 'contentReady' signal which is handled
    by the 'onContent' callback.
    """

    contentReady = pyqtSignal(str, QWebEngineUrlRequestJob, str, bytes)

    def __init__(self, app, parent=None):
        super(NativeIPFSSchemeHandler, self).__init__(parent)

        self.app = app
        self.requests = {}
        self.contentReady.connect(self.onContent)

    def debug(self, msg):
        log.debug('Native scheme handler: {}'.format(msg))

    def onRequestDestroyed(self, uid):
        if uid in self.requests:
            del self.requests[uid]

    def onContent(self, uid, request, ctype, data):
        self.reply(uid, request, ctype, data)

    def reply(self, uid, request, ctype, data, parent=None):
        """
        We're using a mutex here but it shouldn't be necessary
        """

        if uid not in self.requests:
            # Destroyed ?
            return

        mutex = self.requests[uid]['mutex']
        mutex.lock()

        try:
            buf = self.requests[uid]['iodev']
            buf.open(QIODevice.WriteOnly)
            buf.write(data)
            buf.seek(0)
            buf.close()
            request.reply(ctype.encode('ascii'), buf)
            mutex.unlock()
        except Exception:
            log.debug('Error buffering request data')
            request.fail(QWebEngineUrlRequestJob.RequestFailed)
            mutex.unlock()

    async def directoryListing(self, request, client, path):
        currentIpfsPath = IPFSPath(path)

        if not currentIpfsPath.valid:
            self.debug('Invalid path: {0}'.format(path))
            return

        ctx = {}
        try:
            listing = await client.core.ls(path)
        except aioipfs.APIError:
            self.debug('Error listing directory for path: {0}'.format(path))
            return None

        if 'Objects' not in listing:
            return None

        ctx['path'] = path
        ctx['links'] = []

        for obj in listing['Objects']:
            if not isinstance(obj, dict) or 'Hash' not in obj:
                continue

            if obj['Hash'] == path:
                ctx['links'] += obj.get('Links', [])

        for lnk in ctx['links']:
            child = currentIpfsPath.child(lnk['Name'])
            lnk['href'] = child.ipfsUrl

        try:
            data = await renderTemplate('ipfsdirlisting.html', **ctx)
        except:
            self.debug('Failed to render directory listing template')
        else:
            return data.encode()

    async def renderDirectory(self, request, client, path):
        ipfsPath = IPFSPath(path)
        indexPath = ipfsPath.child('index.html')

        try:
            data = await client.cat(str(indexPath))
        except aioipfs.APIError as exc:
            dec = APIErrorDecoder(exc)

            if dec.errNoSuchLink():
                return await self.directoryListing(request, client, path)

            return self.urlInvalid(request)
        else:
            return data

    async def renderDagListing(self, request, client, path, **kw):
        return b'ENOTIMPLEMENTED'

    async def renderDagNode(self, request, client, ipfsPath, **kw):
        self.debug('DAG node render: {}'.format(ipfsPath))
        indexPath = ipfsPath.child('index.html')

        try:
            data = await client.cat(str(indexPath))
            if not data:
                return await self.renderDagListing(request, client, ipfsPath,
                                                   **kw)
        except aioipfs.APIError:
            return await self.renderDagListing(request, client, ipfsPath, **kw)
        else:
            return data

    async def renderData(self, request, data, uid):
        rUrl = request.requestUrl()
        cType = await detectMimeTypeFromBuffer(data[0:512])

        if cType:
            self.contentReady.emit(uid, request, cType.type, data)
        else:
            self.debug('Impossible to detect MIME type for {0}'.format(
                rUrl.toString()))

    @ipfsOp
    async def handleRequest(self, ipfsop, request, uid):
        rUrl = request.requestUrl()

        if not rUrl.isValid():
            self.debug('Invalid URL: {}'.format(rUrl.toString()))
            return self.urlInvalid(request)

        scheme = rUrl.scheme()

        if scheme == SCHEME_IPFS:
            # hostname = base32-encoded CID
            cid = rUrl.host()

            if not ipfsRegSearchCid32(cid):
                return self.urlInvalid(request)

            ipfsPathS = joinIpfs(cid) + rUrl.path()
        elif scheme == SCHEME_IPNS:
            ipfsPathS = joinIpns(rUrl.host()) + rUrl.path()
        else:
            return self.urlInvalid(request)

        ipfsPath = IPFSPath(ipfsPathS)
        if not ipfsPath.valid:
            return self.urlInvalid(request)

        return await self.fetchFromPath(ipfsop, request, ipfsPath, uid)

    async def fetchFromPath(self, ipfsop, request, ipfsPath, uid, **kw):
        try:
            data = await ipfsop.client.cat(str(ipfsPath))
        except aioipfs.APIError as exc:
            await asyncio.sleep(0)

            self.debug('API error ({path}): {err}'.format(
                path=str(ipfsPath), err=exc.message)
            )

            dec = APIErrorDecoder(exc)

            if dec.errNoSuchLink():
                return self.urlNotFound(request)

            if dec.errIsDirectory():
                data = await self.renderDirectory(
                    request,
                    ipfsop.client,
                    str(ipfsPath)
                )
                if data:
                    return await self.renderData(request, data, uid)

            if dec.errUnknownNode():
                # DAG / TODO
                data = await self.renderDagNode(
                    request,
                    ipfsop.client,
                    ipfsPath
                )
                if data:
                    return await self.renderData(request, data, uid)
        else:
            return await self.renderData(request, data, uid)

    def requestStarted(self, request):
        uid = str(uuid.uuid4())
        self.requests[uid] = {
            'request': request,
            'iodev': QBuffer(parent=request),
            'mutex': QMutex()
        }

        request.destroyed.connect(
            functools.partial(self.onRequestDestroyed, uid))
        ensure(self.handleRequest(request, uid))


class ObjectProxySchemeHandler(NativeIPFSSchemeHandler):
    """
    This scheme handler acts as a "proxy" to an IPFS path.

    For example, by mapping the url scheme 'docs' to this path:

    /ipfs/bafybeihw6pfoai7wbyt5jhbiialicees3vn336fkrdmjlbheh2dqsxsmlu/

    Accessing 'docs:/pdf/today.pdf' will access the IPFS object at

    /ipfs/bafybeihw6pfoai7wbyt5jhbiialicees3vn336fkrdmjlbheh2dqsxsmlu/pdf/today.pdf
    """

    def __init__(self, app, ipfsPath, parent=None):
        """
        :param IPFSPath ipfsPath: the path to proxy to
        """
        super(ObjectProxySchemeHandler, self).__init__(app, parent=parent)

        self.proxiedPath = ipfsPath

    @ipfsOp
    async def handleRequest(self, ipfsop, request, uid):
        if not self.proxiedPath.valid:
            return request.fail(QWebEngineUrlRequestJob.UrlInvalid)

        rUrl = request.requestUrl()

        if not rUrl.isValid():
            return self.urlInvalid(request)

        path = rUrl.path()
        ipfsPath = self.proxiedPath.child(path)

        if not ipfsPath.valid:
            return self.urlInvalid(request)

        return await self.fetchFromPath(ipfsop, request, ipfsPath, uid)


class DAGProxySchemeHandler(NativeIPFSSchemeHandler):
    """
    This scheme handler acts as a "proxy" to a DAG
    """

    def __init__(self, app, parent=None):
        super(DAGProxySchemeHandler, self).__init__(app, parent=parent)

        # The DAG being proxied
        self.proxied = None

    async def getDag(self):
        raise Exception('implement getDag()')

    async def renderDagListing(self, request, client, path):
        listing = await self.proxied.list(
            path=path.subPath if path.subPath else '')
        if not listing:
            return b'ELISTING'

        ctx = {}
        ctx['path'] = str(path)
        ctx['links'] = []

        for nname in listing:
            child = path.child(nname)
            ctx['links'].append({
                'name': nname,
                'href': child.ipfsUrl
            })

        try:
            data = await renderTemplate('ipfsdagnodelisting.html', **ctx)
        except:
            pass
        else:
            return data.encode()

    @ipfsOp
    async def handleRequest(self, ipfsop, request, uid):
        if self.proxied is None:
            self.proxied = await self.getDag()

        if not self.proxied:
            return request.fail(QWebEngineUrlRequestJob.UrlInvalid)

        rUrl = request.requestUrl()

        if not rUrl.isValid():
            self.debug('Invalid URL: {}'.format(rUrl.toString()))
            return self.urlInvalid(request)

        path = rUrl.path()
        ipfsPathS = joinIpfs(self.proxied.dagCid) + path

        ipfsPath = IPFSPath(ipfsPathS)
        if not ipfsPath.valid:
            return self.urlInvalid(request)

        return await self.fetchFromPath(ipfsop, request, ipfsPath, uid)


class GalacteekSchemeHandler(DAGProxySchemeHandler):
    @ipfsOp
    async def getDag(self, ipfsop):
        curProfile = ipfsop.ctx.currentProfile
        if curProfile:
            return curProfile.dagUser


class DAGWatchSchemeHandler(DAGProxySchemeHandler):
    def __init__(self, app, dappName, parent=None):
        super(DAGWatchSchemeHandler, self).__init__(app, parent=parent)

        self.name = dappName
        self.app.towers['dags'].dappDeployedAtCid.connect(self.onDappDeployed)

    def onDappDeployed(self, dag, name, cid):
        if name == self.name:
            self.proxied = dag

    @ipfsOp
    async def getDag(self, ipfsop):
        return self.proxied


class DWebSchemeHandler(BaseURLSchemeHandler):
    """
    IPFS dweb scheme handler, supporting URLs such as:

        dweb:/ipfs/multihash
        dweb:/ipns/domain.com/path
        dweb://ipfs/multihash/...
        fs:/ipfs/multihash
        etc..
    """

    def __init__(self, app, parent=None):
        QWebEngineUrlSchemeHandler.__init__(self, parent)
        self.app = app

    def redirectIpfs(self, request, path, url):
        yUrl = URL(url.toString())
        if len(yUrl.parts) < 3:
            return None

        newUrl = self.app.subUrl(path)

        if url.hasFragment():
            newUrl.setFragment(url.fragment())
        if url.hasQuery():
            newUrl.setQuery(url.query())

        return request.redirect(newUrl)

    def requestStarted(self, request):
        url = request.requestUrl()

        if url is None:
            return

        scheme = url.scheme()

        if scheme in [SCHEME_FS, SCHEME_DWEB]:
            # Take leading slashes out of the way
            urlStr = url.toString()
            urlStr = re.sub(
                r'^{scheme}:(\/)+'.format(scheme=scheme),
                '{scheme}:/'.format(scheme=scheme),
                urlStr
            )
            url = QUrl(urlStr)
        else:
            log.debug('Unsupported scheme')
            return

        path = url.path()
        if not isinstance(path, str):
            self.urlInvalid(request)
            return

        log.debug(
            'IPFS scheme handler req: {url} {scheme} {path} {method}'.format(
                url=url.toString(), scheme=scheme, path=path,
                method=request.requestMethod()))

        if path.startswith('/ipfs/') or path.startswith('/ipns/'):
            try:
                return self.redirectIpfs(request, path, url)
            except Exception as err:
                log.debug('Exception handling request: {}'.format(str(err)))


class MultiDAGProxySchemeHandler(NativeIPFSSchemeHandler):
    """
    Proxy handler to a stack of DAGs (first DAG registered is the
    first DAG tried).
    """

    def __init__(self, app, parent=None):
        super(MultiDAGProxySchemeHandler, self).__init__(app, parent=parent)
        self.proxied = []

    def useDag(self, dag):
        self.proxied.append(dag)

    async def renderDagListing(self, request, client, path, **kw):
        dag = kw.pop('dag', None)
        assert dag is not None

        listing = await dag.list(
            path=path.subPath if path.subPath else '')
        if not listing:
            return b'ELISTING'

        ctx = {}
        ctx['path'] = str(path)
        ctx['links'] = []

        for nname in listing:
            child = path.child(nname)
            ctx['links'].append({
                'name': nname,
                'href': child.ipfsUrl
            })

        try:
            data = await renderTemplate('ipfsdagnodelisting.html', **ctx)
        except:
            pass
        else:
            return data.encode()

    @ipfsOp
    async def handleRequest(self, ipfsop, request, uid):
        if len(self.proxied) == 0:
            return self.urlInvalid(request)

        rUrl = request.requestUrl()

        if not rUrl.isValid():
            self.debug('Invalid URL: {}'.format(rUrl.toString()))
            return self.urlInvalid(request)

        path = rUrl.path()

        for dag in self.proxied:
            if not dag.dagCid:
                continue

            ipfsPathS = joinIpfs(dag.dagCid) + path
            ipfsPath = IPFSPath(ipfsPathS)

            if not ipfsPath.valid:
                return request.fail(QWebEngineUrlRequestJob.UrlInvalid)

            return await self.fetchFromPath(ipfsop, request, ipfsPath, uid,
                                            dag=dag)

    async def fetchFromPath(self, ipfsop, request, ipfsPath, uid, **kw):
        dag = kw.pop('dag', None)
        assert dag is not None

        log.debug('Multi DAG proxy : Fetch-from-path {}'.format(ipfsPath))
        try:
            data = await ipfsop.client.cat(str(ipfsPath))
        except aioipfs.APIError as exc:
            await asyncio.sleep(0)

            self.debug('API error ({path}): {err}'.format(
                path=str(ipfsPath), err=exc.message)
            )

            dec = APIErrorDecoder(exc)

            if dec.errNoSuchLink():
                return self.urlNotFound(request)

            if dec.errIsDirectory():
                data = await self.renderDirectory(
                    request,
                    ipfsop.client,
                    str(ipfsPath)
                )
                if data:
                    return await self.renderData(request, data, uid)

            if dec.errUnknownNode():
                # UNK DAG / TODO
                data = await self.renderDagNode(
                    request,
                    ipfsop.client,
                    ipfsPath,
                    dag=dag
                )
                if data:
                    return await self.renderData(request, data, uid)
        else:
            return await self.renderData(request, data, uid)
