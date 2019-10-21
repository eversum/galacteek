from aiohttp import Signal

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal  # noqa


class ASig(Signal):
    pass


class SingleASig(ASig):
    def __init__(self, callback, owner=None):
        super().__init__(owner)

        self.append(callback)
        self.freeze()


class GObject(QObject):
    pass
