import jinja2
import aiofiles
import jinja2.exceptions
import os.path
from datetime import datetime
from dateutil import parser as dateparser
from tempfile import TemporaryDirectory

from galacteek import log
from galacteek.core import isoformat

from galacteek.ipfs.cidhelpers import joinIpfs
from galacteek.ipfs.cidhelpers import cidValid
from galacteek.ipfs.cidhelpers import isIpfsPath
from galacteek.ipfs.cidhelpers import isIpnsPath
from galacteek.ipfs.wrappers import ipfsOpFn

from galacteek.dweb.markdown import markitdown


def tstodate(ts):
    try:
        date = datetime.fromtimestamp(ts)
    except TypeError:
        return ''
    else:
        return isoformat(date, timespec='seconds')


def ipfspathnorm(input):
    if isinstance(input, str):
        if cidValid(input):
            return joinIpfs(input)
        elif isIpfsPath(input) or isIpnsPath(input):
            return input


def markdownconv(text):
    return markitdown(text)


def datetimeclean(datestring):
    try:
        dt = dateparser.parse(datestring)
        if dt:
            return dt.strftime('%Y-%m-%d %H:%M')
    except:
        return None


def defaultJinjaEnv():
    # We use Jinja's async rendering
    env = jinja2.Environment(
        loader=jinja2.PackageLoader('galacteek', 'templates'),
        enable_async=True
    )
    env.filters['tstodate'] = tstodate
    env.filters['ipfspathnorm'] = ipfspathnorm
    env.filters['markdown'] = markdownconv
    env.filters['dtclean'] = datetimeclean
    return env


def renderWrapper(tmpl, **kw):
    try:
        data = tmpl.render(**kw)
    except Exception as err:
        log.debug('Error rendering jinja template',
                  exc_info=err)
        return None
    else:
        return data


async def renderTemplate(tmplname, loop=None, env=None, **kw):
    env = env if env else defaultJinjaEnv()
    tmpl = env.get_template(tmplname)
    if not tmpl:
        raise Exception('template not found')

    data = await tmpl.render_async(**kw)
    return data


@ipfsOpFn
async def ipfsRender(op, env, tmplname, **kw):
    _offline = kw.pop('offline', False)
    tmpl = env.get_template(tmplname)
    if not tmpl:
        raise Exception('template not found')

    try:
        data = await tmpl.render_async(**kw)
        entry = await op.addString(data, offline=_offline)
    except Exception as err:
        log.debug('Could not render web template {0}: {1}'.format(
            tmplname, str(err)))
        return None
    else:
        if entry:
            return entry['Hash']


@ipfsOpFn
async def ipfsRenderContained(op, env, tmplname, **kw):
    """
    Render a template, wrapping the result in a directory
    """

    tmpl = env.get_template(tmplname)
    if not tmpl:
        raise Exception('template not found')

    with TemporaryDirectory() as tmpdir:
        try:
            data = await tmpl.render_async(**kw)

            async with aiofiles.open(os.path.join(
                    tmpdir, 'index.html'), 'w+t') as fd:
                await fd.write(data)

            entry = await op.addPath(tmpdir)
        except Exception as err:
            log.debug('Could not render web template {0}: {1}'.format(
                tmplname, str(err)))
            return None
        else:
            if entry:
                return entry['Hash']
