import functools
import asyncio

from aiohttp.client_exceptions import ClientConnectorError

from PyQt5.QtWidgets import QApplication

from galacteek import log
from galacteek.ipfs.ipfsops import IPFSOpRegistry


def _getOp():
    return IPFSOpRegistry.getDefault()


def appTask(fn, *args, **kw):
    app = QApplication.instance()
    app.task(fn, *args, **kw)


def ipfsOpFn(func):
    @functools.wraps(func)
    async def wrapper(*args, **kw):
        op = IPFSOpRegistry.getDefault()
        if op:
            return await func(op, *args, **kw)
        log.debug('ipfsopfn: op is null')
    return wrapper


class ipfsClassW:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.__name__ = wrapped.__name__

    def __repr__(self):
        return self.__name__

    async def _operation(self, inst, op, *args, **kw):
        from galacteek.ipfs import ConnectionError
        try:
            resp = await self.wrapped(inst, op, *args, **kw)
        except GeneratorExit:
            log.debug('GeneratorExit: {inst}'.format(
                inst=inst))
            raise
        except asyncio.CancelledError:
            log.debug('IPFSOp cancelled: {name}'.format(name=self.__name__))
            raise
        except RuntimeError as e:
            log.debug('IPFSOp runtime err: {}'.format(str(e)))
        except ClientConnectorError as e:
            raise ConnectionError(
                'Client connection error: {}'.format(str(e)))
        else:
            return resp


class ipfsOp(ipfsClassW):
    """
    Wraps an async class method, calling it with an IPFSOperator
    """

    def __get__(self, inst, owner):
        async def wrapper(*args, **kw):
            op = IPFSOpRegistry.getDefault()
            if op:
                return await self._operation(inst, op, *args, **kw)

        wrapper.__name__ = self.__name__
        wrapper.__qualname__ = self.__name__
        return wrapper


class ipfsStatOp(ipfsClassW):
    def __get__(self, inst, owner):
        async def wrapper(*args, **kw):
            op = IPFSOpRegistry.getDefault()
            if op is None:
                return

            path = args[0]

            stat = op.objStatCtxGet(path)
            if not stat:
                stat = await op.objStatCtxUpdate(path)

            args = args + (stat,)

            return await self._operation(inst, op, *args, **kw)
        return wrapper
