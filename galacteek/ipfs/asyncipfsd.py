import os
import os.path
import asyncio
import re
import json
import signal
import aioipfs
import aiofiles
import orjson
import psutil

from galacteek import log


def boolarg(arg):
    return str(arg).lower()


async def shell(arg):
    p = await asyncio.create_subprocess_shell((arg),
                                              stdin=asyncio.subprocess.PIPE,
                                              stdout=asyncio.subprocess.PIPE)

    stdout, stderr = await p.communicate()
    return stdout.decode()


async def ipfsConfig(binPath, param, value):
    return await shell("'{0}' config '{1}' '{2}'".format(
        binPath, param, value))


async def ipfsConfigProfileApply(binPath, profile):
    return await shell("'{0}' config profile apply {1}".format(
        binPath, profile))


async def ipfsConfigJson(binPath, param, value):
    return await shell("'{0}' config --json {1} {2}".format(
        binPath, param, json.dumps(value)))


async def ipfsConfigGetJson(binPath, param):
    return await shell("'{0}' config --json '{1}'".format(binPath, param))


class IPFSDProtocol(asyncio.SubprocessProtocol):
    """
    IPFS daemon process protocol

    This handles output from the IPFS daemon
    """

    def __init__(self, loop, exitFuture, startedFuture, debug=False):
        self._loop = loop
        self._debug = debug
        self._output = bytearray()
        self.eventStarted = asyncio.Event()
        self.exitFuture = exitFuture
        self.startedFuture = startedFuture
        self.apiStarted = False
        self.gatewayStarted = False
        self.swarmStarted = False
        self.daemonReady = False
        self.errAlreadyRunning = False

    @property
    def loop(self):
        return self._loop

    @property
    def output(self):
        return self._output

    def pipe_data_received(self, fd, data):
        try:
            msg = data.decode().strip()
        except BaseException:
            return

        # The output we expect might be different in earlier versions
        # i've mainly tested with go-ipfs > 0.4.11
        # TODO: implement ipfs process supervisor independent of daemon output

        for line in msg.split('\n'):
            if self._debug:
                # go-ipfs output
                log.debug(line)
            if re.search('Error: ipfs daemon is running', line):
                self.errAlreadyRunning = True
            if re.search('Gateway.*server listening on', line):
                self.gatewayStarted = True
            if re.search('Swarm listening on', line):
                self.swarmStarted = True
            if re.search('API server listening', line):
                self.apiStarted = True
            if re.search('Daemon is ready', line):
                self.daemonReady = True
            if re.search('Error:', line):
                pass

        if self.daemonReady is True:
            if not self.startedFuture.done():
                self.startedFuture.set_result(True)
            self.eventStarted.set()

        self._output.extend(data)

    def process_exited(self):
        self.exitFuture.set_result(True)


DEFAULT_APIPORT = 5001
DEFAULT_SWARMPORT = 4001
DEFAULT_GWPORT = 8080


class AsyncIPFSDaemon(object):
    """
    Async IPFS daemon subprocess wrapper

    :param str repopath: IPFS repository path
    :param int apiport: API port number to listen on
    :param int swarmport: Swarm port number to listen on
    :param int gatewayport: HTTP GW port number to listen on
    :param int swarmLowWater: min swarm connections
    :param int swarmHighWater: max swarm connections
    :param int storageMax: max repository storage capacity, in GB
    :param bool pubsubEnable: enable pubsub
    :param bool noBootstrap: empty bootstrap
    :param bool corsEnable: enable CORS
    :param bool p2pStreams: enable P2P streams support
    :param bool gwWritable: make the HTTP gateway writable
    """

    def __init__(self, repopath, goIpfsPath='ipfs',
                 statusPath=None,
                 apiport=DEFAULT_APIPORT,
                 swarmport=DEFAULT_SWARMPORT,
                 swarmportQuic=DEFAULT_SWARMPORT,
                 swarmProtos=['tcp', 'quic'],
                 gatewayport=DEFAULT_GWPORT, initRepo=True,
                 swarmLowWater=10, swarmHighWater=20, nice=20,
                 pubsubEnable=False, noBootstrap=False, corsEnable=True,
                 pubsubRouter='floodsub', namesysPubsub=False,
                 pubsubSigning=False, offline=False,
                 fileStore=False,
                 detached=True,
                 p2pStreams=True, migrateRepo=False, routingMode='dht',
                 gwWritable=False, storageMax=20, debug=False, loop=None):

        self.loop = loop if loop else asyncio.get_event_loop()
        self.exitFuture = asyncio.Future(loop=self.loop)
        self.startedFuture = asyncio.Future(loop=self.loop)
        self.repopath = repopath
        self.statusPath = statusPath
        self.detached = detached
        self.goIpfsPath = goIpfsPath
        self.apiport = apiport
        self.gatewayport = gatewayport
        self.swarmport = swarmport
        self.swarmportQuic = swarmportQuic
        self.swarmProtos = swarmProtos
        self.swarmLowWater = swarmLowWater
        self.swarmHighWater = swarmHighWater
        self.storageMax = storageMax
        self.initRepo = initRepo
        self.fileStore = fileStore
        self.namesysPubsub = namesysPubsub
        self.pubsubEnable = pubsubEnable
        self.pubsubRouter = pubsubRouter
        self.pubsubSigning = pubsubSigning
        self.corsEnable = corsEnable
        self.p2pStreams = p2pStreams
        self.noBootstrap = noBootstrap
        self.migrateRepo = migrateRepo
        self.gwWritable = gwWritable
        self.routingMode = routingMode
        self.offline = offline
        self.nice = nice
        self.debug = debug

        self._procPid = None

    @property
    def pid(self):
        return self._procPid

    @property
    def running(self):
        return self.pid is not None

    async def start(self):
        # Set the IPFS_PATH environment variable
        os.environ['IPFS_PATH'] = self.repopath

        log.debug('Using go-ipfs binary: {}'.format(self.goIpfsPath))

        if not os.path.isdir(self.repopath):
            os.mkdir(self.repopath)

        if not os.path.exists(os.path.join(self.repopath, 'config')) or \
                not os.path.isdir(os.path.join(self.repopath, 'datastore')):
            # Pretty sure this is an empty repository path

            log.info('Initializing IPFS repository: {repo}'.format(
                repo=self.repopath))

            await shell('ipfs init')

        apifile = os.path.join(self.repopath, 'api')
        if os.path.exists(apifile):
            os.unlink(apifile)

        # API & gateway multiaddrs
        await self.ipfsConfig(
            'Addresses.API',
            '/ip4/127.0.0.1/tcp/{0}'.format(self.apiport))
        await self.ipfsConfig(
            'Addresses.Gateway',
            '/ip4/127.0.0.1/tcp/{0}'.format(self.gatewayport))

        # Swarm multiaddrs (ipv4 and ipv6), TCP and quic
        swarmAddrs = []

        if 'quic' in self.swarmProtos:
            swarmAddrs += [
                '/ip4/0.0.0.0/udp/{swarmport}/quic'.format(
                    swarmport=self.swarmportQuic),
                '/ip6/::/udp/{swarmport}/quic'.format(
                    swarmport=self.swarmportQuic)
            ]

        if 'tcp' in self.swarmProtos or not swarmAddrs:
            swarmAddrs += [
                '/ip4/0.0.0.0/tcp/{swarmport}'.format(
                    swarmport=self.swarmport),
                '/ip6/::/tcp/{swarmport}'.format(
                    swarmport=self.swarmport)
            ]

        await self.ipfsConfigJson('Addresses.Swarm',
                                  json.dumps(swarmAddrs))

        # Swarm connection manager parameters
        await self.ipfsConfigJson('Swarm.ConnMgr.LowWater',
                                  self.swarmLowWater)
        await self.ipfsConfigJson('Swarm.ConnMgr.HighWater',
                                  self.swarmHighWater)
        await self.ipfsConfig('Swarm.ConnMgr.GracePeriod',
                              '60s')

        await self.ipfsConfig('Routing.Type', self.routingMode)

        if self.pubsubRouter in ['floodsub', 'gossipsub']:
            await self.ipfsConfig('Pubsub.Router',
                                  self.pubsubRouter)

        await self.ipfsConfigJson('Pubsub.DisableSigning',
                                  boolarg(not self.pubsubSigning))

        await self.ipfsConfigJson('Swarm.DisableBandwidthMetrics', 'false')

        # Maximum storage
        await self.ipfsConfig('Datastore.StorageMax',
                              '{0}GB'.format(self.storageMax))

        # P2P streams
        await self.ipfsConfigJson('Experimental.Libp2pStreamMounting',
                                  boolarg(self.p2pStreams)
                                  )

        await self.ipfsConfigJson('Experimental.FilestoreEnabled',
                                  boolarg(self.fileStore)
                                  )

        # CORS
        if self.corsEnable:
            await self.ipfsConfigJson(
                'API.HTTPHeaders.Access-Control-Allow-Credentials',
                '["true"]'
            )
            await self.ipfsConfigJson(
                'API.HTTPHeaders.Access-Control-Allow-Methods',
                '["GET", "POST"]'
            )
            await self.ipfsConfigJson(
                'API.HTTPHeaders.Access-Control-Allow-Origin',
                '["*"]'
            )

        if self.noBootstrap:
            await self.ipfsConfigJson('Bootstrap', '[]')

        await self.ipfsConfigJson('Gateway.Writable',
                                  self.gwWritable)

        args = [self.goIpfsPath, 'daemon']

        if self.pubsubEnable:
            args.append('--enable-pubsub-experiment')

        if self.namesysPubsub:
            args.append('--enable-namesys-pubsub')

        if self.migrateRepo:
            args.append('--migrate')

        if self.offline:
            args.append('--offline')

        pCreationFlags = 0

        f = self.loop.subprocess_exec(
            lambda: IPFSDProtocol(self.loop, self.exitFuture,
                                  self.startedFuture,
                                  debug=self.debug),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=pCreationFlags)

        self.transport, self.proto = await f

        self._procPid = self.transport.get_pid()
        self.setProcLimits(self.pid, nice=self.nice)
        return True

    async def writeStatus(self, client):
        try:
            ident = await client.core.id()
        except aioipfs.APIError:
            return False
        else:
            async with aiofiles.open(self.statusPath, 'w+b') as fd:
                await fd.write(orjson.dumps({
                    'ident': ident,
                    'pid': self._procPid
                }))

            return True

    async def client(self):
        return aioipfs.AsyncIPFS(host='127.0.0.1',
                                 port=self.apiport, loop=self.loop)

    async def loadStatus(self):
        client = await self.client()
        try:
            async with aiofiles.open(self.statusPath, 'r') as fd:
                status = orjson.loads(await fd.read())
                assert 'ident' in status
                assert 'pid' in status

            proc = psutil.Process(status['pid'])

            if proc.status() in ['running', 'sleeping']:
                ident = await client.core.id()
                assert ident['ID'] == status['ident']['ID']
                return True, client
            else:
                return False, None
        except aioipfs.APIError as e:
            log.debug(f'Error loading status: {e.message}')
            await client.close()
            return False, None
        except psutil.NoSuchProcess:
            log.debug('Process is gone')
            await client.close()
            return False, None
        except Exception:
            log.debug('Error loading status')
            await client.close()
            return False, None

    async def ipfsConfig(self, param, value):
        return await ipfsConfig(self.goIpfsPath, param, value)

    async def ipfsConfigJson(self, param, value):
        return await ipfsConfigJson(self.goIpfsPath, param, value)

    async def ipfsConfigGetJson(self, param):
        return await ipfsConfigGetJson(self.goIpfsPath, param)

    async def ipfsConfigPeeringGet(self):
        return await self.ipfsConfigGetJson('Peering.Peers')

    async def ipfsConfigPeeringAdd(self, peerId, addrs=[]):
        """
        Add a peer in the Peering.Peers config parameter
        (new peering system in go-ipfs 0.6)
        """

        _peers = await self.ipfsConfigPeeringGet()

        entry = {
            'ID': peerId,
            'Addrs': addrs
        }

        try:
            pList = json.loads(_peers)

            if not any(e['ID'] == peerId for e in pList):
                pList.append(entry)
        except Exception:
            pList = [entry]

        return await self.ipfsConfigJson(
            'Peering.Peers',
            json.dumps(pList)
        )

    def setProcLimits(self, pid, nice=20):
        try:
            import psutil
        except ImportError:
            return

        log.debug('Applying limits to process: {pid}'.format(pid=pid))

        try:
            proc = psutil.Process(pid)
            proc.nice(nice)
        except Exception:
            log.debug('Could not apply limits to process {pid}'.format(
                pid=pid))

    def stop(self):
        log.debug('Stopping IPFS daemon')
        try:
            self.transport.send_signal(signal.SIGINT)
            self.transport.send_signal(signal.SIGHUP)
            self._procPid = None
            return True
        except Exception as e:
            self._procPid = None
            self.terminateException = e
            return False
