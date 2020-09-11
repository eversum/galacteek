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
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from galacteek.core import datetimeIsoH

from galacteek.core.ps import keyPsJson
from galacteek.core.ps import psSubscriber

from .helpers import getIcon
from .widgets import GalacteekTab


subscriber = psSubscriber('pubsub_sniffer')


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

        subscriber.add_async_listener(keyPsJson, self.onJsonMessage)

    async def onJsonMessage(self, key, message):
        sender, topic, jsonMsg = message

        dItem = QTableWidgetItem(datetimeIsoH())
        tItem = QTableWidgetItem(topic)
        sItem = QTableWidgetItem(sender)

        viewButton = QToolButton()
        viewButton.setIcon(getIcon('search-engine.png'))
        viewButton.clicked.connect(functools.partial(
            self.viewJsonMessage, jsonMsg))

        for item in [dItem, tItem, sItem]:
            item.setFlags(
                Qt.ItemIsSelectable | Qt.ItemIsEnabled)

        curRow = self.tableWidget.rowCount()
        self.tableWidget.insertRow(curRow)
        self.tableWidget.setItem(curRow, 0, dItem)
        self.tableWidget.setItem(curRow, 1, tItem)
        self.tableWidget.setItem(curRow, 2, sItem)
        self.tableWidget.setCellWidget(curRow, 3, viewButton)

    def viewJsonMessage(self, msgJson):
        """
        :param message bytes: raw message data
        """

        dlg = QDialog()
        layout = QVBoxLayout()
        dlg.setLayout(layout)
        dlg.setMinimumSize(
            (2 * self.app.desktopGeometry.width()) / 3,
            (2 * self.app.desktopGeometry.height()) / 3,
        )

        msgView = QTextBrowser(dlg)
        msgView.setFontFamily('Montserrat')
        msgView.setFontWeight(QFont.DemiBold)
        msgView.setFontPointSize(12)
        layout.addWidget(msgView)
        msgView.insertPlainText(
            json.dumps(msgJson, indent=4))

        msgView.moveCursor(QTextCursor.Start)

        dlg.exec_()

    async def onClose(self):
        return True
