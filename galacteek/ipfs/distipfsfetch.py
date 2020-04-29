from async_generator import async_generator, yield_

import aiohttp
import aiofiles
import sys
import os
import os.path
import platform
import tarfile
import zipfile
import tempfile
import asyncio
import shutil


@async_generator
async def distIpfsExtract(dstdir='.', software='go-ipfs', executable='ipfs',
                          site='dist.ipfs.io', version='0.5.0', loop=None,
                          sslverify=True):

    """ Fetch a distribution archive from dist.ipfs.io and extracts the
        wanted executable to dstdir. Yields progress messages """

    arch = None
    osType = None
    exeExt = ''

    pMachine = platform.machine()
    pSystem = platform.system()

    if pMachine == 'x86_64':
        arch = 'amd64'
    elif pMachine == 'i386':
        arch = '386'

    if pSystem == 'Linux':
        osType = 'linux'
        arExt = '.tar.gz'
    elif pSystem == 'Windows':
        osType = 'windows'
        arExt = '.zip'
        exeExt = '.exe'
    elif pSystem == 'FreeBSD':
        osType = 'freebsd'
        arExt = '.tar.gz'
    elif pSystem == 'Darwin':
        osType = 'darwin'
        arExt = '.tar.gz'

    if arch is None or osType is None or arExt is None:
        return False

    tmpDst = tempfile.mkdtemp(prefix='distipfs')
    if not tmpDst:
        return False

    fileName = '{software}_v{version}_{os}-{arch}{ext}'.format(
        software=software, version=version, arch=arch, os=osType, ext=arExt)

    url = 'https://{site}/{software}/v{version}/{filename}'.format(
        software=software, site=site, version=version, arch=arch,
        os=osType, ext=arExt, filename=fileName)

    tmpFile = tempfile.NamedTemporaryFile(suffix=arExt, delete=False)
    arPath = tmpFile.name

    def statusMessage(code, msg):
        return ((code, '{0}: {1}'.format(fileName, msg)))

    await yield_((0, 'Starting download: {0} ...'.format(url)))

    async with aiofiles.open(arPath, 'w+b') as fd:
        bytesRead = 0
        async with aiohttp.ClientSession() as session:
            async with session.get(url, verify_ssl=sslverify) as resp:
                if resp.status == 404:
                    await yield_(statusMessage(
                        0, 'Error downloading (file not found)'))
                    return False
                else:
                    await yield_(statusMessage(0, 'File found!'))

                csize = 524288
                ccount = 0
                while True:
                    data = await resp.content.read(csize)
                    if not data:
                        break

                    ccount += 1
                    await fd.write(data)
                    bytesRead += len(data)

                    if divmod(ccount, 32)[1] == 0:
                        await yield_(statusMessage(
                            0, 'received {} bytes'.format(bytesRead)))
                    await asyncio.sleep(0)

    def extract(path, dest):
        fname = os.path.basename(path)
        if fname.endswith('.zip'):
            opener, mode = zipfile.ZipFile, 'r'
        elif fname.endswith('.tar.gz') or fname.endswith('.tgz'):
            opener, mode = tarfile.open, 'r:gz'
        else:
            # can't handle that
            return False
        try:
            # the path inside the archive.
            execPath = os.path.join(software, executable + exeExt)
            with opener(path, mode=mode) as tf:
                tf.extract(execPath, path=dest)
                shutil.copy(os.path.join(dest, execPath), dstdir)
            os.unlink(arPath)
            shutil.rmtree(dest, ignore_errors=True)
            return True
        except Exception as e:
            print('Could not extract archive file:', str(e), file=sys.stderr)
            os.unlink(arPath)
            return False

    await yield_(statusMessage(0, 'Extracting distribution ..'))
    loop = loop if loop else asyncio.get_event_loop()
    tarF = loop.run_in_executor(None, extract, arPath, tmpDst)
    return await tarF
