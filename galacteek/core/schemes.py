import os.path
import aiohttp
import re
import uuid
import aioipfs

from PyQt5.QtWebEngineCore import QWebEngineUrlSchemeHandler
from PyQt5.QtWebEngineCore import QWebEngineUrlScheme
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestJob
from PyQt5.QtNetwork import QNetworkReply

from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QIODevice
from PyQt5.QtCore import QBuffer
from PyQt5.QtCore import QMutex
from PyQt5.QtCore import QObject, pyqtSignal

from galacteek import log
from galacteek import ensure
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.mimetype import detectMimeTypeFromBuffer
from galacteek.ipfs.cidhelpers import cidValid
from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.dweb.render import renderTemplate

from yarl import URL


SCHEME_DWEB = 'dweb'
SCHEME_FS = 'fs'
SCHEME_IPFS = 'ipfs'
SCHEME_IPNS = 'ipns'


def initializeSchemes():
    name = QWebEngineUrlScheme.schemeByName(SCHEME_DWEB.encode()).name()
    if name:
        return

    schemeDweb = QWebEngineUrlScheme(SCHEME_DWEB.encode())
    schemeDweb.setFlags(QWebEngineUrlScheme.SecureScheme)

    schemeFs = QWebEngineUrlScheme(SCHEME_FS.encode())
    schemeFs.setFlags(QWebEngineUrlScheme.SecureScheme)

    schemeIpfs = QWebEngineUrlScheme(SCHEME_IPFS.encode())
    if 0:
        schemeIpfs.setFlags(
            QWebEngineUrlScheme.SecureScheme |
            QWebEngineUrlScheme.ViewSourceAllowed
        )

    schemeIpns = QWebEngineUrlScheme(SCHEME_IPNS.encode())
    schemeIpns.setFlags(QWebEngineUrlScheme.SecureScheme)

    QWebEngineUrlScheme.registerScheme(schemeDweb)
    QWebEngineUrlScheme.registerScheme(schemeFs)
    QWebEngineUrlScheme.registerScheme(schemeIpfs)
    QWebEngineUrlScheme.registerScheme(schemeIpns)


class Base32IPFSSchemeHandler(QWebEngineUrlSchemeHandler):
    """
    Scheme handler for URLs using the ipfs://<cidbase32> scheme.

    We don't use the gateway at all here, making the async requests
    manually.


    """
    contentReady = pyqtSignal(str, QWebEngineUrlRequestJob, str, bytes)

    def __init__(self, app, parent=None):
        QWebEngineUrlSchemeHandler.__init__(self, parent)

        self.app = app
        self.contentReady.connect(self.onContent)
        self.requests = {}

    def debug(self, msg):
        log.debug('Base32 scheme handler: {}'.format(msg))

    def onRequestDestroyed(self, uid):
        if uid in self.requests:
            self.debug('Req {} was destroyed'.format(uid))
            del self.requests[uid]

    def onContent(self, uid, request, ctype, data):
        self.requests[uid] = {
            'request': request,
            'iodev': QBuffer(parent=request)
        }
        request.destroyed.connect(lambda: self.onRequestDestroyed(uid))
        self.reply(uid, request, ctype, data)

    def reply(self, uid, request, ctype, data, parent=None):
        if uid not in self.requests:
            # Destroyed ?
            return

        try:
            buf = self.requests[uid]['iodev']
            buf.open(QIODevice.WriteOnly)
            buf.write(data)
            buf.seek(0)
            buf.close()
            request.reply(ctype.encode('ascii'), buf)
        except Exception:
            log.debug('Error buffering request data')

    async def directoryListing(self, request, client, path):
        currentIpfsPath = IPFSPath(path)

        if not currentIpfsPath.valid:
            self.debug('Invalid path: {0}'.format(path))
            return

        ctx = {}
        try:
            listing = await client.core.ls(path)
        except aioipfs.APIError as exc:
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
            if exc.code == 0 and exc.message.startswith('no link named'):
                return await self.directoryListing(request, client, path)
            if exc.code == 0 and exc.message == 'this dag node is a directory':
                return await self.directoryListing(request, client, path)
        else:
            return data

    async def renderData(self, request, data):
        cType = await detectMimeTypeFromBuffer(data[0:512])
        uid = str(uuid.uuid4())
        if cType:
            self.contentReady.emit(uid, request, cType.type, data)
        else:
            self.contentReady.emit(uid, request, 'text/plain', 'NO'.encode())

    @ipfsOp
    async def handleRequest(self, ipfsop, request):
        rUrl = request.requestUrl()
        initiator = request.initiator()

        if not rUrl.isValid():
            return

        scheme = rUrl.scheme()
        params = self.app.getIpfsConnectionParams()

        url = None
        if scheme == SCHEME_IPFS:
            # hostname = base32-encoded CID
            cid = rUrl.host()
            if not cidValid(cid):
                return

            ipfsPathS = joinIpfs(cid) + rUrl.path()
        elif scheme == SCHEME_IPNS:
            ipfsPathS = joinIpns(rUrl.host()) + rUrl.path()
        else:
            return

        ipfsPath = IPFSPath(ipfsPathS)
        if not ipfsPath.valid:
            return

        try:
            data = await ipfsop.client.cat(ipfsPathS)
        except aioipfs.APIError as exc:
            if exc.code == 0 and exc.message == 'this dag node is a directory':
                data = await self.renderDirectory(
                    request,
                    ipfsop.client,
                    ipfsPathS
                )
                if data:
                    return await self.renderData(request, data)
        else:
            return await self.renderData(request, data)

    def requestStarted(self, request):
        ensure(self.handleRequest(request))


class DWebSchemeHandler(QWebEngineUrlSchemeHandler):
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
