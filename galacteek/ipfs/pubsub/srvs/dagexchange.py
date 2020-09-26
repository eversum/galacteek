import asyncio
import collections
import secrets
import async_timeout

from galacteek import ensure

from galacteek.core.asynclib import loopTime
from galacteek.core.ps import keyTokensDagExchange
from galacteek.core.ps import keySnakeDagExchange

from galacteek.ipfs.pubsub import TOPIC_DAGEXCH
from galacteek.ipfs.pubsub.service import EncryptedJSONPubsubService
from galacteek.ipfs.pubsub.messages.dagexch import DAGExchangeMessageV1
from galacteek.ipfs import ipfsOp


class PSDAGExchangeService(EncryptedJSONPubsubService):
    hubPublish = False

    def __init__(self, ipfsCtx, client, **kw):
        super().__init__(ipfsCtx, client, TOPIC_DAGEXCH,
                         runPeriodic=True,
                         minMsgTsDiff=60,
                         thrRateLimit=8,
                         thrPeriod=20,
                         thrRetry=5,
                         filterSelfMessages=False, **kw)
        if 0:
            super().__init__(ipfsCtx, client,
                             topic=self.peeredTopic(ipfsCtx.node.id),
                             runPeriodic=True,
                             minMsgTsDiff=60,
                             thrRateLimit=8,
                             thrPeriod=20,
                             thrRetry=5,
                             filterSelfMessages=False, **kw)

        self.__authenticatedDags = collections.deque([], 128)
        self.__serviceToken = secrets.token_hex(64)

    async def processJsonMessage(self, sender, msg):
        msgType = msg.get('msgtype', None)

        peerCtx = self.ipfsCtx.peers.getByPeerId(sender)
        if not peerCtx:
            self.debug('Message from unauthenticated peer: {}'.format(
                sender))
            return

        if msgType == DAGExchangeMessageV1.TYPE:
            await self.handleExchangeMessage(sender, msg)

    async def handleExchangeMessage(self, sender, msg):
        eMsg = DAGExchangeMessageV1(msg)
        if not eMsg.valid():
            self.debug('Invalid DAGExchange message')
            return

        if eMsg.dagClass == 'seeds':
            ensure(self.handleSeedsExchangeMessage(sender, eMsg))

    @ipfsOp
    async def _dagVerifyCidSignature(self, ipfsop, sender: str,
                                     dagCid: str,
                                     token: str,
                                     elixir: str,
                                     pubKeyPem):
        from aiohttp.web_exceptions import HTTPOk

        req = {
            'elixir': elixir,
            'sessiontoken': token
        }

        try:
            with async_timeout.timeout(40):
                async with ipfsop.p2pDialer(
                        sender, 'dagexchange',
                        addressAuto=True) as streamCtx:
                    if streamCtx.failed:
                        raise Exception(f'Cannot dial {sender}')

                    async with streamCtx.session.post(
                            streamCtx.httpUrl('/dagcidsign'),
                            json=req) as resp:
                        if resp.status != HTTPOk.status_code:
                            raise Exception(
                                f'DAG CID sign error {sender}: '
                                f'{resp.status}')

                        payload = await resp.json()
                        assert dagCid in payload

                        if await ipfsop.ctx.rsaExec.pssVerif64(
                                dagCid.encode(),
                                payload[dagCid]['pss64'].encode(),
                                pubKeyPem):
                            self.debug('DAG CID SIGN: {dagCid} OK!')
                            return True
                        else:
                            self.debug('DAG CID SIGN: {dagCid} Wrong!')
                            return False
        except asyncio.TimeoutError:
            self.debug(f'_dagVerifyCidSignature({dagCid}): timeout!')
            return False
        except Exception as err:
            self.debug(f'_dagVerifyCidSignature({dagCid}): error {err}')
            return False

    @ipfsOp
    async def handleSeedsExchangeMessage(self, ipfsop, sender, eMsg):
        profile = ipfsop.ctx.currentProfile
        local = (sender == ipfsop.ctx.node.id)

        if eMsg.dagNet == 'maindagnet':
            self.debug(f'Received seeds exchange message from {sender}')

            dag = profile.dagSeedsAll

            try:
                pubKeyPem = await ipfsop.rsaPubKeyCheckImport(
                    eMsg.signerPubKeyCid)

                if not pubKeyPem:
                    raise Exception(
                        'Could not load pub key for peer {sender}')

                if not local and eMsg.dagCid not in self.__authenticatedDags:
                    if not await self._dagVerifyCidSignature(
                        sender,
                        eMsg.dagCid,
                        eMsg.serviceToken,
                        eMsg.snakeOil[0:64],
                        pubKeyPem
                    ):
                        self.debug(f'DAG exchange: CID SIGWRONG {eMsg.dagCid}')
                        raise Exception(f'CID SIGWRONG {eMsg.dagCid}')
                    else:
                        self.__authenticatedDags.append(eMsg.dagCid)
                        self.debug(f'DAG exchange: CID SIGOK {eMsg.dagCid}')

                await dag.link(
                    sender, eMsg.dagUid, eMsg.dagCid,
                    eMsg.signerPubKeyCid,
                    local=local
                )
            except Exception as err:
                self.debug(f'Exception on DAG exchange: {err}')

            await ipfsop.sleep(3)

            if not local and eMsg.megaDagCid not in self.__authenticatedDags:
                if await self._dagVerifyCidSignature(
                    sender,
                    eMsg.megaDagCid,
                    eMsg.serviceToken,
                    eMsg.snakeOil[64:128],
                    pubKeyPem
                ):
                    self.debug(
                        f'DAG exchange: MCID SIGOK {eMsg.megaDagCid}')

                    # Do the merge
                    await dag.megaMerge(
                        sender, eMsg.megaDagCid,
                        eMsg.signerPubKeyCid,
                        local=local
                    )
                else:
                    self.debug(
                        f'DAG exchange: MCID SIGWRONG {eMsg.megaDagCid}')

    async def onSeedAdded(self, seedCid):
        await self.sendExchangeMessage()

    @ipfsOp
    async def sendExchangeMessage(self, ipfsop):
        self.debug('Sending seeds exchange message')

        seedsDag = ipfsop.ctx.currentProfile.dagSeedsMain
        seedsDagAll = ipfsop.ctx.currentProfile.dagSeedsAll

        oil = secrets.token_hex(64)

        await self.gHubPublish(
            keyTokensDagExchange, {'token': self.__serviceToken})
        await ipfsop.sleep(0.5)

        await self.gHubPublish(
            keySnakeDagExchange, {
                'snakeoil': oil,
                'cids': [
                    seedsDag.dagCid,
                    seedsDagAll.dagCid
                ],
                'expires': loopTime() + 180
            }
        )

        await ipfsop.sleep(0.5)

        pubKeyCid = await ipfsop.rsaAgent.pubKeyCid()

        eMsg = DAGExchangeMessageV1.make(
            seedsDag.dagClass,
            seedsDag.dagCid,
            seedsDag.dagNet,
            seedsDag.dagName,
            seedsDag.uid,
            pubKeyCid,
            seedsDagAll.dagCid,
            self.__serviceToken,
            oil
        )

        await self.send(eMsg)

        self.debug(f'DAGEXCH: Authorized DAGS: {self.__authenticatedDags}')

    @ipfsOp
    async def periodic(self, ipfsop):
        while True:
            if ipfsop.ctx.currentProfile:
                seedsDag = ipfsop.ctx.currentProfile.dagSeedsMain

                if seedsDag.dagUpdated.count() == 0:
                    # Sig not connected yet
                    seedsDag.dagUpdated.connectTo(self.onSeedAdded)

                await self.sendExchangeMessage()
                await asyncio.sleep(60 * 10)
            else:
                # Wait for the DAG
                await asyncio.sleep(5)