from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from .tab_iskanje_ongoing_research import OngoingResearchTab
from .tab_iskanje_completed_research import CompletedResearchTab

class TabIskalnik(QWidget):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface

        # Main layout
        layout = QVBoxLayout(self)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Completed Research Tab
        self.completed_tab = CompletedResearchTab(self.iface)
        self.tabs.addTab(self.completed_tab, "Zaključene raziskave")
        # Ongoing Research Tab
        self.ongoing_tab = OngoingResearchTab(self.iface)
        self.tabs.addTab(self.ongoing_tab, "Trenutne raziskave")


