from collections import UserList
from quamash import QThreadExecutor
import asyncio
import traceback
import functools
from asyncio_extras.file import open_async
import aiofiles

from PyQt5.QtWidgets import QApplication


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

    def count(self):
        return len(self)

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

        app = QApplication.instance()

        if app and hasattr(app, 'shuttingDown') and app.shuttingDown is True:
            # Prevent emitting signals during the app's shutdown
            log.debug(
                '{!r}: Application is shutting down, not emitting'.format(
                    self))
            return

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


def loopTime():
    loop = asyncio.get_event_loop()
    if loop:
        return loop.time()


def ensureGenericCallback(future):
    try:
        future.result()
    except Exception:
        traceback.print_exc()


def ensure(coro, **kw):
    """ 'futcallback' should not be used in the coroutine's kwargs """

    from galacteek import log

    app = QApplication.instance()

    callback = kw.pop('futcallback', ensureGenericCallback)
    future = asyncio.ensure_future(coro, **kw)
    if callback:
        future.add_done_callback(callback)

    if app and hasattr(app, 'cmdArgs') and app.cmdArgs.asynciodebug:
        # Save the cost of debug() calls here..
        lTime = loopTime()
        log.debug(f'Ensured new task (loop time: {lTime}): {future!r}')

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


async def asyncReadFile(path, mode='rb', size=None):
    try:
        async with aiofiles.open(path, mode) as fd:
            if size:
                return await fd.read(size)
            else:
                return await fd.read()
    except BaseException:
        return None


async def asyncReadTextFileChunked(path, mode='rt', chunksize=8192):
    try:
        async with open_async(path, mode) as f:
            async for chunk in f.async_readchunks(chunksize):
                yield chunk
    except BaseException as err:
        print(str(err))


async def asyncWriteFile(path, data, mode='w+b'):
    try:
        async with aiofiles.open(path, mode) as fd:
            await fd.write(data)
    except BaseException:
        return None


async def threadExec(fn, *args):
    loop = asyncio.get_event_loop()

    with QThreadExecutor(1) as texec:
        return await loop.run_in_executor(texec, fn, *args)


def _all_tasks(loop=None):
    """For compat with py3.5 and py3.6"""
    try:
        return asyncio.all_tasks(loop=loop)
    except AttributeError:
        return {t for t in asyncio.Task.all_tasks(loop=loop) if not t.done()}


async def cancelAllTasks(*, timeout=None, raise_timeout_error=False):
    """
    From sakaio.sakaio.cancel_all_tasks (version 3.0 not on pypi)

    https://github.com/nitely/sakaio
    """

    from galacteek import log

    def _warn_pending():
        running = _all_tasks(loop=loop)
        if running:
            log.debug(
                'There are {tc} pending tasks, first 10: {first}',
                tc=len(running), first=list(running)[:10])

    loop = asyncio.get_event_loop()
    running = _all_tasks(loop=loop)

    for t in running:
        t.cancel()

    for f in asyncio.as_completed(running, timeout=timeout, loop=loop):
        try:
            await f
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            _warn_pending()
            if raise_timeout_error:
                raise
        except Exception:
            log.warning('Task Error!', exc_info=True)
            pass

    # Tasks scheduled by clean-ups or
    # by tasks ignoring cancellation
    _warn_pending()
