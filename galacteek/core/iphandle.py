import re
import random


ipHandleRe = re.compile(
    r'^(?P<username>\w{1,32})' +
    r'(#?(?P<rid>[0-9]{1,9}))?' +
    r'@(?P<vplanet>\w{1,64})' +
    r'(@?(?P<peer>(\w{46,59})))?$'
)


class SpaceHandle:
    def __init__(self, handle):
        self._handle = handle
        self.m = ipHandleMatch(handle) if isinstance(handle, str) else None

    @property
    def valid(self):
        return self.m is not None

    @property
    def peer(self):
        if self.valid:
            return self.m.group('peer')

    @property
    def vPlanet(self):
        if self.valid:
            return self.m.group('vplanet')

    @property
    def username(self):
        if self.valid:
            return self.m.group('username')

    @property
    def human(self):
        if self.valid:
            return ipHandleGen(
                self.m.group('username'),
                self.m.group('vplanet')
            )

    @property
    def short(self):
        if self.valid:
            peer = self.m.group('peer')

            if peer:
                return ipHandleGen(
                    self.m.group('username'),
                    self.m.group('vplanet'),
                    peerId=peer[32:]
                )
            else:
                return ipHandleGen(
                    self.m.group('username'),
                    self.m.group('vplanet')
                )

    def __str__(self):
        return self._handle if self._handle else 'Invalid Handle'


def ipHandleMatch(handle):
    return ipHandleRe.match(handle)


def ipHandleGen(username, vPlanet, rand=False, peerId=None):
    if rand is True:
        r = random.Random()
        username = '{u}#{rid}'.format(u=username, rid=r.randint(1, 99999))

    iphandle = '{username}@{vplanet}'.format(
        username=username,
        vplanet=vPlanet
    )

    if peerId:
        iphandle += '@{p}'.format(p=peerId)

    return iphandle


def ipHandlePeer(handle):
    match = ipHandleRe.match(handle)
    if match:
        return match.group('peer')


def ipHandleUsername(handle):
    match = ipHandleRe.match(handle)
    if match:
        return match.group('username')
