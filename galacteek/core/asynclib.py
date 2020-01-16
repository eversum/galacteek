from collections import UserList
import asyncio
import traceback
import functools
import aiofiles


class AsyncSignal(UserList):
    """
    Async signal.

    Similar to aiohttp.Signal but no need to freeze the
    callback list. Adding signals works by just using append()
    """

    def __init__(self, *signature, **kw):
        super().__init__()
        self._id = kw.pop('_id', 'no id')
        self._sig = signature

    def __str__(self):
        return '<AsyncSignal({id}): signature: {!r}>'.format(
            list(self._sig), id='no id')

    def disconnect(self, cbk):
        try:
            for receiver in self:
                if receiver == cbk:
                    self.remove(cbk)
        except Exception:
            pass

    def connectTo(self, callback):
        self.append(callback)

    async def emit(self, *args, **kwargs):
        from galacteek import log

        if len(args) != len(self._sig):
            log.debug(
                '{!r}: does not match signature: {} !'.format(
                    self, *args))
            return

        for receiver in self:
            try:
                if isinstance(receiver, functools.partial) and \
                        asyncio.iscoroutinefunction(receiver.func):
                    await receiver.func(*(receiver.args + args), **kwargs)
                elif isinstance(receiver, functools.partial) and \
                        callable(receiver.func):
                    receiver.func(*(receiver.args + args), **kwargs)
                elif asyncio.iscoroutinefunction(receiver):
                    await receiver(*args, **kwargs)
            except Exception as err:
                log.debug(
                    '{!r}: callback: {cbk}: exception at emission: {e}'.format(
                        self, cbk=receiver, e=str(err)))
                traceback.print_exc()
                continue


def ensureGenericCallback(future):
    try:
        future.result()
    except Exception:
        traceback.print_exc()


def ensure(coro, **kw):
    """ 'futcallback' should not be used in the coroutine's kwargs """
    callback = kw.pop('futcallback', ensureGenericCallback)
    future = asyncio.ensure_future(coro, **kw)
    if callback:
        future.add_done_callback(callback)
    return future


def partialEnsure(coro, *args, **kw):
    def _pwrapper(coro, *args, **kw):
        ensure(coro(*args, **kw))

    return functools.partial(_pwrapper, coro, *args, **kw)


def soonish(cbk, *args, **kw):
    """ Soon. Or a bit later .. """
    loop = kw.pop('loop', asyncio.get_event_loop())
    loop.call_soon(functools.partial(cbk, *args, **kw))


def ensureLater(delay: int, coro, *args, **kw):
    loop = asyncio.get_event_loop()
    loop.call_later(delay, ensure, coro(*args, **kw))


class asyncify:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.name = wrapped.__name__

    def __get__(self, inst, owner):
        def wrapper(*args, **kw):
            return asyncio.ensure_future(self.wrapped(inst, *args, **kw))
        return wrapper


def asyncifyfn(fn):
    @functools.wraps(fn)
    def ensureFn(*args, **kwargs):
        return asyncio.ensure_future(fn(*args, **kwargs))
    return ensureFn


def callAt(loop, callback, delay, *args, **kw):
    now = loop.time()
    return loop.call_at(now + delay, callback, *args)


def async_enterable(f):
    """

    From aioftp.common

    Decorator. Bring coroutine result up, so it can be used as async context

    ::

        >>> async def foo():
        ...
        ...     ...
        ...     return AsyncContextInstance(...)
        ...
        ... ctx = await foo()
        ... async with ctx:
        ...
        ...     # do

    ::

        >>> @async_enterable
        ... async def foo():
        ...
        ...     ...
        ...     return AsyncContextInstance(...)
        ...
        ... async with foo() as ctx:
        ...
        ...     # do
        ...
        ... ctx = await foo()
        ... async with ctx:
        ...
        ...     # do

    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):

        class AsyncEnterableInstance:

            async def __aenter__(self):
                self.context = await f(*args, **kwargs)
                return await self.context.__aenter__()

            async def __aexit__(self, *args, **kwargs):
                await self.context.__aexit__(*args, **kwargs)

            def __await__(self):
                return f(*args, **kwargs).__await__()

        return AsyncEnterableInstance()

    return wrapper


async def asyncReadFile(path, mode='rb'):
    try:
        async with aiofiles.open(path, mode) as fd:
            return await fd.read()
    except BaseException:
        return None


async def asyncWriteFile(path, data, mode='w+b'):
    try:
        async with aiofiles.open(path, mode) as fd:
            await fd.write(data)
    except BaseException:
        return None
