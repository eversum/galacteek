# You need the pytest-qt plugin to run these tests

import pytest

from PyQt5.QtCore import Qt

from .cidtest import *

from galacteek.ui import dialogs
from galacteek.appsettings import *
from galacteek.ipfs.wrappers import *
from galacteek.ipfs.ipfsops import *


class TestCIDDialogs:
    # Valid and invalid CID lists
    @pytest.mark.parametrize('validcid0', validcid0)
    @pytest.mark.parametrize('validcid1', validcid1)
    @pytest.mark.parametrize('invalidcid', invalidcids)
    def test_singlecidinput(self, qtbot, validcid0, validcid1, invalidcid):
        dlg = dialogs.IPFSCIDInputDialog()
        qtbot.addWidget(dlg)

        self.cidInput(qtbot, dlg, validcid0)
        assert dlg.validCid is True
        assert dlg.ui.validity.text() == 'Valid CID version 0'

        dlg.clearCID()
        self.cidInput(qtbot, dlg, validcid1)
        assert dlg.validCid is True
        assert dlg.ui.validity.text() == 'Valid CID version 1'

        dlg.clearCID()
        self.cidInput(qtbot, dlg, invalidcid)
        assert dlg.validCid is False

    @pytest.mark.parametrize('validcid0', validcid0)
    def test_mulcidinput(self, qtbot, validcid0):
        dlg = dialogs.IPFSMultipleCIDInputDialog()
        qtbot.addWidget(dlg)

        self.cidInput(qtbot, dlg, validcid0)
        qtbot.mouseClick(dlg.ui.addCidButton, Qt.LeftButton)

        cidList = dlg.getCIDs()
        assert len(cidList) == 1
        assert cidList.pop() == validcid0

    def cidInput(self, qtbot, dlg, cid):
        # Manually input the CID character by character
        # The whole unit test is a bit cpu-intensive since the dialog will
        # check CID's validity on every char input but hey ..
        for char in cid:
            qtbot.keyPress(dlg.ui.cid, char)
