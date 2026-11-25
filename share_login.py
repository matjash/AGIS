# -*- coding: utf-8 -*-
"""Login to the network share with the organisation settings file.

Used when the file server answers (CPA network or VPN) but the file cannot be read:
a home PC or another Windows account without credentials for the share. AGIS opens the
folder in File Explorer, Windows shows its own login window ("Zapomni si moje
poverilnice"), and AGIS checks again every few seconds until the file can be read.
"""

import os
import sys

from qgis.PyQt.QtCore import QTimer, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QPushButton
from qgis.core import Qgis, QgsApplication, QgsTask

from . import config
from .externals import cpa_available

POLL_MS = 3000
POLL_MAX = 60          # about three minutes

MESSAGE = ("AGIS ne more prebrati nastavitev CPA – Windows potrebuje vašo prijavo "
           "v omrežni disk.")


def open_share():
    """Open the folder of the settings file; Windows asks for the login if needed."""
    folder = config.settings_folder()
    if not folder:
        return False
    if sys.platform.startswith("win"):
        os.startfile(folder)            # pylint: disable=no-member
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
    return True


class ShareLogin:
    """One per plugin: the message bar notice, the login button and the re-check after it."""

    def __init__(self, iface, on_success):
        self.iface = iface
        self.on_success = on_success
        self.notified = False           # the notice is shown once per QGIS session
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._check)
        self._polls = 0
        self._task = None

    def notify_if_needed(self):
        """Show the notice once per session when the share needs a login."""
        if self.notified or not config.org_needs_login():
            return
        self.notified = True
        bar = self.iface.messageBar()
        item = bar.createMessage("AGIS", MESSAGE)
        button = QPushButton("Prijava v omrežni disk")
        button.clicked.connect(lambda: (bar.popWidget(item), self.start()))
        item.layout().addWidget(button)
        bar.pushWidget(item, Qgis.MessageLevel.Warning)

    def start(self):
        """Open the share in File Explorer, then check again until it can be read."""
        if not open_share():
            return
        self._polls = 0
        self._timer.start(POLL_MS)

    def stop(self):
        self._timer.stop()

    def _check(self):
        if self._task is not None:
            return
        self._polls += 1
        self._task = QgsTask.fromFunction("AGIS: nastavitve organizacije",
                                          lambda task: cpa_available(refresh=True),
                                          on_finished=self._checked)
        QgsApplication.taskManager().addTask(self._task)

    def _checked(self, exception, result=None):
        self._task = None
        path, _status = config.org_settings_info()
        if exception is None and path and path == config.get("settings_file"):
            self.iface.messageBar().pushMessage("AGIS", "Nastavitve CPA so prebrane.", Qgis.MessageLevel.Success, 5)
            self.on_success()
            return
        if self._polls < POLL_MAX:
            self._timer.start(POLL_MS)
