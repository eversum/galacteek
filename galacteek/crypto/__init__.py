import asyncio
import concurrent.futures
import functools


class BaseCryptoExec:
    def __init__(self, loop=None, executor=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.executor = executor if executor else \
            concurrent.futures.ThreadPoolExecutor(max_workers=4)

    async def _exec(self, fn, *args, **kw):
        return await self.loop.run_in_executor(
            self.executor, functools.partial(fn, *args, **kw))
