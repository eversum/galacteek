from PyQt5.QtGui import QMovie
from PyQt5.QtGui import QIcon


class BaseClip(QMovie):
    def __init__(self, clipname='rotating-cube.gif', cache=True, speed=100):
        super(BaseClip, self).__init__(
            ':share/clips/{}'.format(clipname))
        self.setSpeed(speed)

        self.setCacheMode(
            QMovie.CacheAll if cache is True else QMovie.CacheNone)

    def createIcon(self):
        return QIcon(self.currentPixmap())

    def playing(self):
        return self.state() == QMovie.Running


class RotatingCubeClipSimple(BaseClip):
    def __init__(self, **kw):
        super().__init__(clipname='rotating-cube.gif', **kw)


class RotatingCubeRedFlash140d(BaseClip):
    def __init__(self, **kw):
        super().__init__(clipname='rotating-cube-redflash-140-6fps.gif', **kw)


class RotatingCubeClipFunky(BaseClip):
    def __init__(self, **kw):
        super().__init__(clipname='funky-cube-1.gif', **kw)
