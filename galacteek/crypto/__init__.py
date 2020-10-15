import asyncio
import concurrent.futures
import functools

from cachetools import TTLCache


class BaseCryptoExec:
    def __init__(self, loop=None, executor=None,
                 cacheSize=128, cacheTTL=120):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.executor = executor if executor else \
            concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._keysCache = TTLCache(maxsize=cacheSize, ttl=cacheTTL)

    async def _exec(self, fn, *args, **kw):
        return await self.loop.run_in_executor(
            self.executor, functools.partial(fn, *args, **kw))

    def cachedKey(self, keyId):
        return self._keysCache.get(keyId)

    def cacheKey(self, keyId, data):
        self._keysCache[keyId] = data
