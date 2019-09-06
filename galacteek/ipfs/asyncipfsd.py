import os
import os.path
import asyncio
import re
import json
import signal

from galacteek import log


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

    def __init__(self, loop, exitFuture, startedFuture):
        self._loop = loop
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
                 apiport=DEFAULT_APIPORT,
                 swarmport=DEFAULT_SWARMPORT,
                 gatewayport=DEFAULT_GWPORT, initRepo=True,
                 swarmLowWater=10, swarmHighWater=20, nice=20,
                 pubsubEnable=False, noBootstrap=False, corsEnable=True,
                 pubsubRouter='floodsub', namesysPubsub=False,
                 p2pStreams=False, migrateRepo=False, routingMode='dht',
                 gwWritable=False, storageMax=20, debug=False, loop=None):

        self.loop = loop if loop else asyncio.get_event_loop()
        self.exitFuture = asyncio.Future(loop=self.loop)
        self.startedFuture = asyncio.Future(loop=self.loop)
        self.repopath = repopath
        self.goIpfsPath = goIpfsPath
        self.apiport = apiport
        self.gatewayport = gatewayport
        self.swarmport = swarmport
        self.swarmLowWater = swarmLowWater
        self.swarmHighWater = swarmHighWater
        self.storageMax = storageMax
        self.initRepo = initRepo
        self.namesysPubsub = namesysPubsub
        self.pubsubEnable = pubsubEnable
        self.pubsubRouter = pubsubRouter
        self.corsEnable = corsEnable
        self.p2pStreams = p2pStreams
        self.noBootstrap = noBootstrap
        self.migrateRepo = migrateRepo
        self.gwWritable = gwWritable
        self.routingMode = routingMode
        self.nice = nice
        self.debug = debug

    async def start(self):
        # Set the IPFS_PATH environment variable
        os.environ['IPFS_PATH'] = self.repopath

        if not os.path.isdir(self.repopath):
            os.mkdir(self.repopath)

        if not os.path.exists(os.path.join(self.repopath, 'config')) or \
                not os.path.isdir(os.path.join(self.repopath, 'datastore')):
            # Pretty sure this is an empty repository path
            await shell('ipfs init')

        apifile = os.path.join(self.repopath, 'api')
        if os.path.exists(apifile):
            os.unlink(apifile)

        # Change the addresses/ports we listen on
        await ipfsConfig(self.goIpfsPath, 'Addresses.API',
                         '/ip4/127.0.0.1/tcp/{0}'.format(self.apiport))
        await ipfsConfig(self.goIpfsPath, 'Addresses.Gateway',
                         '/ip4/127.0.0.1/tcp/{0}'.format(self.gatewayport))

        # Swarm multiaddrs (ipv4 and ipv6)
        swarmAddrs = [
            "/ip4/0.0.0.0/tcp/{swarmport}".format(swarmport=self.swarmport),
            "/ip6/::/tcp/{swarmport}".format(swarmport=self.swarmport)
        ]

        await ipfsConfigJson(self.goIpfsPath, 'Addresses.Swarm',
                             json.dumps(swarmAddrs))

        # Swarm connection manager parameters
        await ipfsConfigJson(self.goIpfsPath, 'Swarm.ConnMgr.LowWater',
                             self.swarmLowWater)
        await ipfsConfigJson(self.goIpfsPath, 'Swarm.ConnMgr.HighWater',
                             self.swarmHighWater)
        await ipfsConfig(self.goIpfsPath, 'Swarm.ConnMgr.GracePeriod',
                         '60s')

        await ipfsConfig(self.goIpfsPath, 'Routing.Type', self.routingMode)

        if self.pubsubRouter in ['floodsub', 'gossipsub']:
            await ipfsConfig(self.goIpfsPath, 'Pubsub.Router',
                             self.pubsubRouter)

        await ipfsConfigJson(self.goIpfsPath,
                             'Swarm.DisableBandwidthMetrics', 'true')

        # Maximum storage
        await ipfsConfig(self.goIpfsPath, 'Datastore.StorageMax',
                         '{0}GB'.format(self.storageMax))

        # P2P streams
        if self.p2pStreams:
            await ipfsConfigJson(self.goIpfsPath,
                                 'Experimental.Libp2pStreamMounting',
                                 'true'
                                 )

        # CORS
        if self.corsEnable:
            # Setup the CORS headers, only allowing the gateway's origin
            await ipfsConfigJson(
                self.goIpfsPath,
                'API.HTTPHeaders.Access-Control-Allow-Credentials',
                '["true"]'
            )
            await ipfsConfigJson(
                self.goIpfsPath,
                'API.HTTPHeaders.Access-Control-Allow-Methods',
                '["GET", "POST"]'
            )
            await ipfsConfigJson(
                self.goIpfsPath,
                'API.HTTPHeaders.Access-Control-Allow-Origin',
                '["*"]'
            )

        if self.noBootstrap:
            await ipfsConfigJson(self.goIpfsPath, 'Bootstrap', '[]')

        await ipfsConfigJson(self.goIpfsPath, 'Gateway.Writable',
                             self.gwWritable)

        args = [self.goIpfsPath, 'daemon']

        if self.pubsubEnable:
            args.append('--enable-pubsub-experiment')

        if self.namesysPubsub:
            args.append('--enable-namesys-pubsub')

        if self.migrateRepo:
            args.append('--migrate')

        f = self.loop.subprocess_exec(
            lambda: IPFSDProtocol(self.loop, self.exitFuture,
                                  self.startedFuture),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        self.transport, self.proto = await f

        proc_pid = self.transport.get_pid()
        self.setProcLimits(proc_pid, nice=self.nice)
        return True

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
            return True
        except Exception as e:
            self.terminateException = e
            return False
