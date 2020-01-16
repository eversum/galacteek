import json
import asyncio
import aioipfs

from urllib.parse import urlparse

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek import log

from pyld.jsonld import JsonLdError


async def aioipfs_document_loader(ipfsClient, loop=None,
                                  secure=False, **kwargs):
    if loop is None:
        loop = asyncio.get_event_loop()

    async def async_loader(client, url):
        """
        :param url: the URL to retrieve.

        :return: the RemoteDocument.
        """
        try:
            if url.startswith('ipschema://'):
                o = urlparse(url)
                kList = await client.key.list()

                ipnsKey = None
                for key in kList['Keys']:
                    if key['Name'] == o.netloc:
                        ipnsKey = key['Id']

                if ipnsKey is None:
                    path = None
                else:
                    path = IPFSPath(joinIpns(ipnsKey)).child(o.path)
            else:
                path = IPFSPath(url)
                if not path.valid:
                    raise Exception('Not a valid path')

            if path and path.valid:
                data = await client.cat(path.objPath)

                return {
                    'document': json.loads(data.decode()),
                    'documentUrl': url,
                    'contextUrl': None
                }

        except aioipfs.APIError as e:
            log.debug(str(e))
            raise e
        except JsonLdError as e:
            log.debug(str(e))
            raise e
        except Exception as cause:
            raise JsonLdError(
                'Could not retrieve a JSON-LD document from the URL.',
                'jsonld.LoadDocumentError', code='loading document failed',
                cause=cause)

    async def loader(url):
        """
        Retrieves JSON-LD at the given URL.

        :param url: the URL to retrieve.

        :return: the RemoteDocument.
        """
        return await async_loader(ipfsClient, url)

    return loader
