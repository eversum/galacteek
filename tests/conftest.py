import pytest
import aioipfs

from galacteek.core import glogger
from galacteek.ipfs.ipfsops import IPFSOperator
from galacteek.ipfs.ipfsops import IPFSOpRegistry
from galacteek.ipfs import asyncipfsd


glogger.basicConfig(level='DEBUG')


@pytest.fixture
def localipfsclient():
    client = aioipfs.AsyncIPFS(host='127.0.0.1', port=5001)
    yield client


@pytest.fixture(scope='session')
def localipfsop(localipfsclient):
    op = IPFSOperator(localipfsclient)
    IPFSOpRegistry.regDefault(op)
    yield op


apiport = 9005
gwport = 9081
swarmport = 9003


@pytest.fixture()
def ipfsdaemon(event_loop, tmpdir):
    dir = tmpdir.mkdir('ipfsdaemon')
    daemon = asyncipfsd.AsyncIPFSDaemon(str(dir),
                                        apiport=apiport,
                                        gatewayport=gwport,
                                        swarmport=swarmport,
                                        loop=event_loop,
                                        pubsubEnable=False,
                                        p2pStreams=True,
                                        noBootstrap=True,
                                        migrateRepo=True
                                        )
    return daemon


@pytest.fixture()
def ipfsdaemon2(event_loop, tmpdir):
    dir = tmpdir.mkdir('ipfsdaemon2')
    daemon = asyncipfsd.AsyncIPFSDaemon(str(dir),
                                        apiport=apiport + 10,
                                        gatewayport=gwport + 10,
                                        swarmport=swarmport + 10,
                                        loop=event_loop,
                                        noBootstrap=True,
                                        pubsubEnable=False,
                                        p2pStreams=True
                                        )
    return daemon


@pytest.fixture()
def iclient(event_loop):
    return aioipfs.AsyncIPFS(port=apiport, loop=event_loop)


@pytest.fixture()
def iclient2(event_loop):
    return aioipfs.AsyncIPFS(port=apiport + 10, loop=event_loop)


@pytest.fixture()
def ipfsop(iclient):
    return IPFSOperator(iclient, debug=True)


async def startDaemons(loop, d1, d2, *args, **kw):
    started1 = await d1.start()
    started2 = await d2.start()

    assert started1 is True, started2 is True

    await asyncio.gather(*[
        d1.proto.eventStarted.wait(),
        d2.proto.eventStarted.wait()
    ])


def stopDaemons(d1, d2):
    d1.stop()
    d2.stop()
