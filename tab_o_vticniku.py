from qgis.PyQt.QtWidgets import QWidget

class TabOVticniku(QWidget):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface