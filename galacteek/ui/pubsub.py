import functools
import json

from PyQt5.QtWidgets import QDialog
from PyQt5.QtWidgets import QTextBrowser

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtWidgets import QTableWidget
from PyQt5.QtWidgets import QVBoxLayout
from PyQt5.QtWidgets import QHeaderView
from PyQt5.QtWidgets import QToolButton

from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import Qt

from galacteek.ipfs.wrappers import ipfsOp
from galacteek.core import datetimeIsoH
from galacteek import ensure
from galacteek import log

from .helpers import getIcon
from .widgets import GalacteekTab


class PubsubSnifferWidget(GalacteekTab):
    def __init__(self, gWindow):
        super(PubsubSnifferWidget, self).__init__(gWindow)

        self.tableWidget = QTableWidget(self)
        self.tableWidget.setHorizontalHeaderLabels(
            ['Date', 'Topic', 'Sender', ''])
        self.tableWidget.setColumnCount(4)
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.horizontalHeader().hide()

        horizHeader = self.tableWidget.horizontalHeader()
        horizHeader.setSectionResizeMode(QHeaderView.ResizeToContents)
        self.vLayout.addWidget(self.tableWidget)

        ensure(self.startListening())

    @ipfsOp
    async def startListening(self, ipfsop):
        for topic, service in ipfsop.ctx.pubsub.services.items():
            log.debug('Listening on topic {}'.format(topic))
            service.rawMessageReceived.connectTo(self.rawMsgReceived)

    async def rawMsgReceived(self, sender, topic, message):
        dItem = QTableWidgetItem(datetimeIsoH())
        tItem = QTableWidgetItem(topic)
        sItem = QTableWidgetItem(sender)

        viewButton = QToolButton()
        viewButton.setIcon(getIcon('search-engine.png'))
        viewButton.clicked.connect(functools.partial(
            self.viewRawMessage, message))

        for item in [dItem, tItem, sItem]:
            item.setFlags(
                Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        curRow = self.tableWidget.rowCount()
        self.tableWidget.insertRow(curRow)
        self.tableWidget.setItem(curRow, 0, dItem)
        self.tableWidget.setItem(curRow, 1, tItem)
        self.tableWidget.setItem(curRow, 2, sItem)
        self.tableWidget.setCellWidget(curRow, 3, viewButton)

    def viewRawMessage(self, message):
        """
        :param message bytes: raw message data
        """

        try:
            msgText = message.decode()
        except Exception:
            return

        try:
            msgJson = json.loads(msgText)
        except Exception:
            msgJson = None

        dlg = QDialog()
        layout = QVBoxLayout()
        dlg.setLayout(layout)
        dlg.setMinimumSize(
            (2 * self.app.desktopGeometry.width()) / 3,
            (2 * self.app.desktopGeometry.height()) / 3,
        )

        msgView = QTextBrowser(dlg)
        layout.addWidget(msgView)
        if msgJson:
            msgView.insertPlainText(
                json.dumps(msgJson, indent=4))
        else:
            msgView.insertPlainText(msgText)

        msgView.moveCursor(QTextCursor.Start)

        # msgView.show()
        dlg.exec_()

    def onClose(self):
        for topic, service in self.app.ipfsCtx.pubsub.services.items():
            service.rawMessageReceived.disconnect(self.rawMsgReceived)

        return True
