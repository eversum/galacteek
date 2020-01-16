import asyncio

from functools import wraps
from cachetools import LRUCache

__all__ = ['amlrucache']


def _wrap_coroutine_storage(cache_dict, key, future):
    async def wrapper():
        val = await future
        cache_dict[key] = val
        return val
    return wrapper()


def _wrap_value_in_coroutine(val):
    async def wrapper():
        return val
    return wrapper()


def amlrucache(f):
    """
    LRU caches the results of a coroutine method

    Uses the repr of the method's object as the cache key
    """
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        _cache = getattr(self, 'cache', LRUCache(128))
        key = repr(self)

        try:
            val = _cache[key]
            if asyncio.iscoroutinefunction(f):
                return _wrap_value_in_coroutine(val)
            return val
        except KeyError:
            val = f(self, *args, **kwargs)

            if asyncio.iscoroutine(val):
                return _wrap_coroutine_storage(_cache, key, val)

            _cache[key] = val
            return val

    return wrapper
