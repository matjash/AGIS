from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel,
    QScrollArea, QFrame, QGridLayout
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon, QFont, QPixmap
from .externals import pn_path


class TabOVticniku(QWidget):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        tabs.addTab(self._build_o_vticniku(), "O vtičniku")
        tabs.addTab(self._build_pomoc(), "Navodila za uporabo")
        
        layout.addWidget(tabs)

    # ------------------------------------------------------------------

    def _scrollable(self, widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _section_label(self, text):
        lbl = QLabel(text)
        font = QFont()
        font.setBold(True)
        lbl.setFont(font)
        lbl.setStyleSheet("margin-top: 8px; color: #4caf50;")
        return lbl

    # ------------------------------------------------------------------

    def _build_o_vticniku(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Logo
        #logo_path = str(pn_path("icons") / "agis_logo.png")
        #logo = QLabel()
        #px = QPixmap(logo_path)
        #if not px.isNull():
        #    logo.setPixmap(px.scaledToWidth(64, Qt.TransformationMode.SmoothTransformation))
        #logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        #layout.addWidget(logo)

        title = QLabel("<h2>AGIS</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel("<i>različica 2.0.0</i>")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: grey;")
        layout.addWidget(version)

        layout.addWidget(self._section_label("Opis"))
        opis = QLabel(
            "AGIS je vtičnik za QGIS, namenjen arheologom in strokovnjakom, ki "
            "delajo na območju Republike Slovenije. Vtičnik omogoča hitro nalaganje "
            "standardiziranih GIS slojev – ortofoto posnetkov, katastrskih podatkov, "
            "lidarskih izdelkov, evidenc dediščine in drugih prostorskih virov."
        )
        opis.setWordWrap(True)
        layout.addWidget(opis)


        layout.addWidget(self._section_label("Podatkovni viri"))
        viri = QLabel(
            "Vsebine vtičnika so pridobljene iz javnih podatkovnih zbirk, ki jih zagotavljajo različni državni organi in institucije, ti so navedeni v opisu posameznih slojev."
            " Vtičnik ne vsebuje lastnih podatkov, temveč deluje kot vmesnik za dostop do obstoječih virov." 
        )
        viri.setWordWrap(True)
        layout.addWidget(viri)


        layout.addWidget(self._section_label("Vzdrževanje"))
        vzdrzevanje = QLabel(
            "Vtičnik vzdržuje <b>Center za preventivno arheologijo (CPA), ZVKDS</b>. "
        )
        vzdrzevanje.setWordWrap(True)
        layout.addWidget(vzdrzevanje)


        layout.addWidget(self._section_label("Avtor"))
        avtor = QLabel("Matjaž Mori, ZUM d. o. o. — <a href='mailto:matjaz.mori@gmail.com'>matjaz.mori@gmail.com</a>")
        avtor.setOpenExternalLinks(True)
        layout.addWidget(avtor)

        layout.addWidget(self._section_label("Povezave"))
        repo = QLabel("<a href='https://github.com/matjash/AGIS'>GitHub repozitorij</a> &nbsp;|&nbsp; "
                      "<a href='https://github.com/matjash/AGIS/issues'>Poročaj o napaki</a>")
        repo.setOpenExternalLinks(True)
        layout.addWidget(repo)

        layout.addStretch()
        return self._scrollable(w)

    # ------------------------------------------------------------------

    def _build_pomoc(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        layout.addWidget(self._section_label("Nalaganje slojev"))
        navodila = QLabel(
            "1. V zavihku <b>Naloži sloje</b> poiščite željeni sloj v seznamu.<br>"
            "2. Sloj naložite z <b>dvojnim klikom</b> na vrstico.<br>"
            "3. Za nalaganje več slojev hkrati izberite vrstice (Ctrl+klik) "
            "in uporabite <b>desni klik → Naloži izbrane sloje</b>.<br>"
            "4. Med nalaganjem se prikaže zelena vrstica napredka. "
            "Nalaganje lahko prekinete z gumbom <b>✕</b>.<br>"
            "5. Gumb <b>↺</b> osveži seznam slojev iz baze."
        )
        navodila.setTextFormat(Qt.TextFormat.RichText)
        navodila.setWordWrap(True)
        layout.addWidget(navodila)

        layout.addWidget(self._section_label("Iskanje"))
        iskanje = QLabel(
            "V polje <b>Išči vire...</b> vpišite del naziva ali opisa sloja. "
            "Seznam se filtrira sproti med tipkanjem."
        )
        iskanje.setTextFormat(Qt.TextFormat.RichText)
        iskanje.setWordWrap(True)
        layout.addWidget(iskanje)

        layout.addWidget(self._section_label("Pomen ikon"))

        icons_data = [
            ("sourcetype_wms.png",    "WMS",              "Spletna kartografska storitev (rasterski sloj)"),
            ("sourcetype_wfs.png",    "WFS",              "Spletna vektorska storitev"),
            ("sourcetype_qlr.png",    "QLR / Definicija", "Predpripravljeni paket slojev (skupina)"),
            ("sourcetype_arcgis.png", "ArcGIS strežnik",  "Sloj s strežnika ArcGIS REST")

        ]

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(2, 1)

        for i, (icon_file, name, desc) in enumerate(icons_data):
            icon_lbl = QLabel()
            px = QPixmap(str(pn_path("icons") / icon_file))
            if not px.isNull():
                icon_lbl.setPixmap(px.scaledToWidth(20, Qt.TransformationMode.SmoothTransformation))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            name_lbl = QLabel(f"<b>{name}</b>")
            name_lbl.setTextFormat(Qt.TextFormat.RichText)

            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)

            grid.addWidget(icon_lbl, i, 0)
            grid.addWidget(name_lbl, i, 1)
            grid.addWidget(desc_lbl, i, 2)

        layout.addWidget(grid_widget)

        layout.addWidget(self._section_label("Statusna vrstica"))
        status = QLabel(
            "Tanka barvna črta na vrhu zavihka <b>Naloži sloje</b> prikazuje stanje povezave z bazo CPA:<br>"
            "• <span style='color:#4caf50'><b>Zelena</b></span> — povezava z bazo CPA vzpostavljena<br>"
            "• <b>Siva</b> — ni povezave z bazo CPA, uporabljeni so lokalni viri"
        )
        status.setTextFormat(Qt.TextFormat.RichText)
        status.setWordWrap(True)
        layout.addWidget(status)

        layout.addStretch()
        return self._scrollable(w)               