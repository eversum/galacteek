
import pytest
import asyncio

from galacteek.database import initOrm
from galacteek.database import closeOrm
from galacteek.core.chattokens import PubChatTokensManager


class TestChatTokens:
    @pytest.mark.asyncio
    async def test_manager(self, dbpath):
        await initOrm(dbpath)

        manager = PubChatTokensManager(inactiveMax=4)
        await manager.start()

        token = await manager.reg(
            'bafkreiccwmdhji2mi4n65ts3tryl7zxhsr72zwbh7eddn24fbvqqyrbaf4',
            '#galacteek', 'g.ddd.222222222',
            'Qmabcd',
            did='did:ipid:bafkreiccwmdhji2mi4n65ts3tryl7zxhsr72zwbh7edd')
        assert token is not None

        fetched = await manager.tokenGet(
            'bafkreiccwmdhji2mi4n65ts3tryl7zxhsr72zwbh7eddn24fbvqqyrbaf4')
        assert fetched is not None
        assert fetched.channel == '#galacteek'
        assert fetched.peerId == 'Qmabcd'

        token = await manager.reg(
            'bafkreiccwmdhji2mi4n65ts3tryl7zxhsr72zwbh7eddn24fbvqqyrbaf3',
            '#galacteek', 'g.ddd.222222222',
            'Qmabce',
            did='did:ipid:bafkreiccwmdhji2mi4n65ts3tryl7zxhsr72zwbh7edb')

        tokens = [t async for t in manager.tokensByChannel('#galacteek')]
        assert len(tokens) == 2

        await asyncio.sleep(5)
        await manager.cleanup()

        tokens = [t async for t in manager.tokensByChannel('#galacteek')]
        assert len(tokens) == 0

        await closeOrm()
