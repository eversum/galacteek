from yarl import URL
import aiohttp
import asyncio
import async_timeout
import re

from galacteek import log
from galacteek.ipfs.cidhelpers import IPFSPath


whoisApiHost = 'api.whoisens.org'
whoisBaseUrl = URL.build(host=whoisApiHost,
                         port=443,
                         scheme='https')


async def ensContentHash(domain, sslverify=True, timeout=8):
    """
    Resolve the content hash of an ENS domain

    :rtype: IPFSPath
    """

    url = whoisBaseUrl.join(URL('resolve/contenthash/{domain}'.format(
        domain=domain)))

    try:
        with async_timeout.timeout(timeout):
            async with aiohttp.ClientSession() as session:
                async with session.get(str(url), verify_ssl=sslverify) as resp:
                    data = await resp.json()
                    addr = data['result']['result']

                    if isinstance(addr, str) and addr.startswith('ipfs://'):
                        match = re.search(
                            'ipfs://(?P<cid>[A-Za-z0-9]+)$', addr)
                        if match:
                            return IPFSPath(match.group('cid'),
                                            autoCidConv=True)
    except asyncio.TimeoutError:
        return None
    except Exception:
        log.debug('ensContentHash: Error occured while resolving')
        return None


async def ensResolveAddr(domain, sslverify=True, timeout=8):
    """
    Resolve the address of an ENS domain
    """

    url = whoisBaseUrl.join(URL('resolve/address/{domain}'.format(
        domain=domain)))

    try:
        with async_timeout.timeout(timeout):
            async with aiohttp.ClientSession() as session:
                async with session.get(str(url), verify_ssl=sslverify) as resp:
                    data = await resp.json()
                    return data['result']['result']
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None
