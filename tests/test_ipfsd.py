import pytest

import asyncio


class TestIPFSD:
    @pytest.mark.asyncio
    async def test_basic(self, event_loop, ipfsdaemon, iclient, ipfsop):
        async def tests(op):
            await op.client.core.id()

            await op.filesList('/')
            r = await op.client.add_json({'a': 123})
            assert await op.filesLink(r, '/')

            await op.client.close()

        def cbstarted(f):
            event_loop.create_task(tests(ipfsop))

        started = await ipfsdaemon.start()
        assert started

        await ipfsdaemon.proto.eventStarted.wait()
        await tests(ipfsop)

        ipfsdaemon.stop()
        await asyncio.wait([ipfsdaemon.exitFuture])
