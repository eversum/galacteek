
from PyQt5.QtWidgets import QStyle
from PyQt5.QtWidgets import QProxyStyle


class GalacteekStyle(QProxyStyle):
    def __init__(self, baseStyle='Fusion'):
        super().__init__(baseStyle)

    def pixelMetric(self, metric, option, widget):
        if metric == QStyle.PM_ToolBarIconSize:
            return 24
        elif metric == QStyle.PM_TabBarIconSize:
            return 16
        elif metric == QStyle.PM_ToolBarItemSpacing:
            return 0
        elif metric == QStyle.PM_ToolBarItemMargin:
            return 0
        elif metric == QStyle.PM_TreeViewIndentation:
            return 25
        else:
            return super().pixelMetric(metric, option, widget)

    def styleHint(self, hint, option, widget, returnData):
        if hint == QStyle.SH_Menu_FlashTriggeredItem:
            return int(True)
        elif hint == QStyle.SH_ToolTip_WakeUpDelay:
            return 600
        elif hint == QStyle.SH_ToolTip_FallAsleepDelay:
            return 800
        else:
            return super().styleHint(hint, option, widget, returnData)
