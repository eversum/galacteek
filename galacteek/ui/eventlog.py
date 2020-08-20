import json
import asyncio

from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHBoxLayout
from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtWidgets import QPushButton

from PyQt5.QtCore import Qt
from PyQt5.QtCore import QSaveFile
from PyQt5.QtCore import QIODevice

from galacteek import log
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ui.widgets import GalacteekTab
from galacteek.ui.helpers import saveFileSelect, messageBox
from galacteek.core import jtraverse


class EventLogWidget(GalacteekTab):
    """
    Widget to display IPFS log events
    """

    def __init__(self, gWindow):
        super().__init__(gWindow)

        self.logZone = QTextEdit()
        self.logZone.setReadOnly(True)

        self.saveButton = QPushButton('Save')
        self.saveButton.clicked.connect(self.onSave)
        self.clearButton = QPushButton('Clear')
        self.clearButton.clicked.connect(lambda: self.logZone.clear())

        layout = QVBoxLayout()
        hLayout = QHBoxLayout()

        self.checkCore = QCheckBox('Core events')
        self.checkCore.setCheckState(Qt.Checked)
        self.checkPubsub = QCheckBox('Pubsub events')
        self.checkDht = QCheckBox('DHT events')
        self.checkBitswap = QCheckBox('Bitswap events')
        self.checkSwarm = QCheckBox('Swarm events')
        self.checkAll = QCheckBox('All events')
        self.checkAll.stateChanged.connect(self.onCheckAll)

        hLayout.addWidget(self.checkCore)
        hLayout.addWidget(self.checkSwarm)
        hLayout.addWidget(self.checkDht)
        hLayout.addWidget(self.checkPubsub)
        hLayout.addWidget(self.checkBitswap)
        hLayout.addWidget(self.checkAll)
        hLayout.addWidget(self.clearButton)
        hLayout.addWidget(self.saveButton)

        layout.addLayout(hLayout)
        layout.addWidget(self.logZone)

        self.tskLog = self.app.task(self.logWatch)
        self.vLayout.addLayout(layout)

    def onCheckAll(self, state):
        self.checkCore.setEnabled(not state)
        self.checkDht.setEnabled(not state)
        self.checkBitswap.setEnabled(not state)
        self.checkPubsub.setEnabled(not state)
        self.checkSwarm.setEnabled(not state)

    def onSave(self):
        fPath = saveFileSelect()
        if fPath:
            file = QSaveFile(fPath)

            if not file.open(QIODevice.WriteOnly):
                return messageBox('Cannot open file for writing')

            file.write(self.logZone.toPlainText().encode())
            file.commit()

    def displayEvent(self, event):
        self.logZone.append(json.dumps(event, indent=4))

    @ipfsOp
    async def logWatch(self, op):
        try:
            await op.client.log.level('all', 'info')

            async for event in op.client.log.tail():
                display = False
                parser = jtraverse.traverseParser(event)

                systems = [parser.traverse('system'),
                           parser.traverse('Tags.system')]

                if ('core' in systems or 'addrutil' in systems) and \
                        self.checkCore.isChecked():
                    display = True
                elif ('swarm' in systems or 'swarm2' in systems) and \
                        self.checkSwarm.isChecked():
                    display = True
                elif 'dht' in systems and self.checkDht.isChecked():
                    display = True
                elif 'bitswap' in systems and self.checkBitswap.isChecked():
                    display = True
                elif 'pubsub' in systems and self.checkPubsub.isChecked():
                    display = True

                if self.checkAll.isChecked():
                    display = True

                if display is True:
                    self.displayEvent(event)

                await op.sleep()

        except asyncio.CancelledError:
            return
        except Exception:
            log.debug('Unknown error ocurred while reading ipfs log')

    async def onClose(self):
        self.tskLog.cancel()
        return True
