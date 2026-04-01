from qgis.PyQt.QtWidgets import QDockWidget, QTabWidget, QWidget, QVBoxLayout, QLabel, QHBoxLayout
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt

class AgisPanel(QDockWidget):
    def __init__(self, iface, load_icon_path, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle('AGIS')
        self.setObjectName('AgisPanel')
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        # Title bar with icon
        icon = QIcon(load_icon_path)
        title_widget = QWidget()
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(4, 2, 4, 2)
        icon_label = QLabel()
        icon_label.setPixmap(icon.pixmap(20, 20))
        title_layout.addWidget(icon_label)
        title_layout.addWidget(QLabel('<b>AGIS</b>'))
        title_widget.setLayout(title_layout)
        self.setTitleBarWidget(title_widget)
        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(QWidget(), 'Naloži sloje')
        self.tabs.addTab(QWidget(), 'eArheologija')
        self.tabs.addTab(QWidget(), 'O vtičniku')
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        main_widget.setLayout(main_layout)
        self.setWidget(main_widget)
        # For later: expose tab widgets for module logic
        self.tab_widgets = {
            'Naloži sloje': self.tabs.widget(0),
            'eArheologija': self.tabs.widget(1),
            'O vtičniku': self.tabs.widget(2)
        }
