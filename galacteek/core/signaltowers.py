
from .objects import GObject
from .objects import pyqtSignal


from galacteek.ipfs.dag import EvolvingDAG


class DAGSignalsTower(GObject):
    dappDeployedAtCid = pyqtSignal(EvolvingDAG, str, str)


class URLSchemesTower(GObject):
    qMappingsChanged = pyqtSignal()
