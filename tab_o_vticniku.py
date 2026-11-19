from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel,
    QScrollArea, QFrame
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
import configparser

from .externals import pn_path


def plugin_version():
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(pn_path("plugin") / "metadata.txt", encoding="utf-8")
    return cp.get("general", "version", fallback="?")


class TabOVticniku(QWidget):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        tabs.addTab(self._build_pomoc(), "Navodila za uporabo")
        tabs.addTab(self._build_o_vticniku(), "O vtičniku")
        
        
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

        version = QLabel(f"<i>različica {plugin_version()}</i>")
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


        layout.addWidget(self._section_label("Razvoj"))
        vzdrzevanje = QLabel(
            "Vtičnik je razvit v okviru <b>Centra za preventivno arheologijo (CPA), ZVKDS</b>."
        )
        vzdrzevanje.setWordWrap(True)
        layout.addWidget(vzdrzevanje)


        layout.addWidget(self._section_label("Avtor"))
        avtor = QLabel("Matjaž Mori — <a href='mailto:matjaz.mori@gmail.com'>matjaz.mori@gmail.com</a>")
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

    def _text(self, html):
        label = QLabel(html)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        return label

    def _build_pomoc(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        layout.addWidget(self._section_label("Nalaganje slojev"))
        layout.addWidget(self._text(
            "1. V zavihku <b>Naloži sloje</b> poiščite vir (polje <b>Išči vire...</b> filtrira sproti).<br>"
            "2. Vir naložite z <b>dvojnim klikom</b> – doda se nad izbrani sloj v panelu <b>Sloji</b> "
            "(oz. na vrh izbrane skupine), brez izbire pa na vrh.<br>"
            "3. Vir lahko tudi <b>povlečete</b> v panel <b>Sloji</b> točno tja, kamor ga želite.<br>"
            "4. Več virov hkrati: izberite vrstice (Ctrl+klik) in <b>desni klik → Naloži</b> ali jih povlecite.<br>"
            "5. Nalaganje lahko prekinete z gumbom <b>✕</b>.<br>"
            "6. Gumb <b>↺</b> osveži kataloge in ponovno preveri povezavo z bazo CPA.<br>"
            "7. Iskanje upošteva naziv, opis, izvor in <b>oznake</b> (ključne besede vira).<br>"
            "Hitro okno samo s seznamom virov odpre ikona s tremi pikami v orodni vrstici AGIS."))

        layout.addWidget(self._section_label("Katalogi"))
        layout.addWidget(self._text(
            "<span style='color:#2e7d32'>●</span> <b>Katalog CPA</b> — viri CPA, vidni samo v omrežju CPA.<br>"
            "<b>∴ Katalog AGIS</b> — skupni seznam virov (vedno na vrhu), "
            "ki se ob zagonu prenese z GitHuba (izklop v zavihku <b>Nastavitve</b>).<br>"
            "<span style='color:#ef6c00'>●</span> <b>Moji viri</b> — vaši viri, shranjeni samo v vašem QGIS-u.<br>"
            "Skriti viri so prikazani sivo, ko vklopite <b>⋯ → Pokaži skrite vire</b>."))

        layout.addWidget(self._section_label("Dodajanje in urejanje virov"))
        layout.addWidget(self._text(
            "1. Sloj ali skupino pripravite v QGIS-u (slog, oznake, merila) in jo izberite v panelu <b>Sloji</b>.<br>"
            "2. V AGIS kliknite <b>+</b>, izpolnite naziv in opis ter izberite katalog.<br>"
            "AGIS pred shranjevanjem odstrani osebna gesla, opozori na lokalne datoteke "
            "in lokalne slike (SVG) vdela v slog, da vir deluje vsem enako.<br><br>"
            "Desni klik na vir: <b>Uredi podatke</b>, <b>Zamenjaj z izbranim</b> (npr. ko se spremeni naslov storitve), "
            "<b>Razveljavi zadnjo zamenjavo</b>, <b>Skrij</b> / <b>Prikaži</b>, <b>Kopiraj v Moji viri</b>. "
            "Katalog CPA lahko ureja le skrbnik s svojo prijavo v bazo CPA."))

        layout.addWidget(self._section_label("Parcele"))
        layout.addWidget(self._text(
            "<b>Iskanje parcele</b>: vpišite K.O. (šifro ali ime) in številko parcele, nato <b>Poišči</b> "
            "(približa in označi) ali <b>Naloži kot sloj</b>.<br>"
            "<b>Parcele pod slojem</b>: <b>Naloži parcele</b> naloži vse parcele pod izbranim slojem "
            "(po želji samo pod izbranimi objekti in z odmikom – negativen odmik območje zmanjša). "
            "<b>Izpiši seznam parcel</b> jih izpiše kot besedilo za kopiranje, npr. "
            "<i>123/1, 125 in 130/4, vse k. o. TRNOVSKO PREDMESTJE (1722)</i>.<br>"
            "Vir: najprej lokalna kopija katastra v bazi CPA, nato GURS WFS; če parcele v kopiji ni, "
            "AGIS preveri še GURS. Brez obojega uporabi vaš sloj, ki ga izberete v zavihku <b>Nastavitve</b> "
            "(AGIS si zapomni njegov vir, zato deluje v vsakem projektu). "
            "Pod gumbi je vedno zapisano, iz katerega vira je rezultat."))

        layout.addWidget(self._section_label("eArheologija in eVRD"))
        layout.addWidget(self._text(
            "Iskanje po arheoloških raziskavah (zaključene in v teku) in po registru nepremične kulturne "
            "dediščine. Podatki so iz kopije v bazi CPA, sicer z geohub.gov.si – vir je zapisan nad tabelo.<br>"
            "<b>Dvojni klik</b> približa na zapis, <b>desni klik</b>: več informacij, prikaz geometrije in "
            "(pri zaključenih raziskavah) odpiranje poročil. <b>Le v obsegu karte</b> pokaže samo zapise "
            "na trenutnem izseku karte. Sloja za karto sta v zavihku <b>Naloži sloje</b>."))

        layout.addWidget(self._section_label("Nastavitve"))
        layout.addWidget(self._text(
            "Vklop kataloga AGIS, lasten sloj parcel in naslovi spletnih storitev (GURS WFS, "
            "eArheologija, eVRD) – vsak z gumbom <b>↺</b> za privzeti naslov. Spremembe se shranijo takoj."))

        layout.addStretch()
        return self._scrollable(w)               