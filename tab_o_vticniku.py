from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel,
    QScrollArea, QFrame
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
import configparser

from .externals import pn_path


TH = ":/images/themes/default/"
REFRESH = f'<img src="{TH}mActionRefresh.svg" width="16" height="16">'
ADD = f'<img src="{TH}symbologyAdd.svg" width="16" height="16">'
EDIT = f'<img src="{TH}mActionToggleEditing.svg" width="16" height="16">'
STOP = '<img src="' + str(pn_path("icons") / "stop.png").replace("\\", "/") + '" width="16" height="16">'


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

        tabs.addTab(self._build_o_vticniku(), "O vtičniku")
        tabs.addTab(self._build_pomoc(), "Navodila za uporabo")
        
        layout.addWidget(tabs)

    # ------------------------------------------------------------------

    def _scrollable(self, widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # Always show the scroll bar: with wrapping text, a scroll bar that appears and disappears
        # changes the width, which changes the wrapping, … - Qt can loop forever (QGIS freezes).
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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


        layout.addWidget(self._section_label("Vzdrževanje"))
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
            "5. Nalaganje ustavite z rdečim gumbom " + STOP + ".<br>"
            "6. Gumb " + REFRESH + " osveži kataloge ter ponovno preveri povezavo z bazo CPA in dosegljivost virov.<br>"
            "7. Iskanje upošteva naziv, opis, izvor in <b>oznake</b> (ključne besede vira).<br>"
            "8. Rdeč <b>!</b> pomeni, da del vira s tega računalnika ni dosegljiv (npr. omrežni pogon ali spletna storitev, ki zahteva prijavo); "
            "podrobnosti so v nasvetu in v <b>desni klik → Podrobnosti</b>. Sivi viri niso dosegljivi, a jih lahko vseeno naložite. "
            "Vir ima lahko <b>nadomestni vir</b>, ki se naloži, ko glavni ni dosegljiv.<br>"
            "9. Vire, ki jih ne potrebujete, skrijete z desnim klikom → <b>Skrij (samo zame)</b>; "
            "vrnete jih prek ⋯ → Pokaži skrite vire.<br>"
            "10. Gumbi katalogov pod seznamom (npr. <b>Katalog AGIS [25]</b>) s klikom skrijejo ali prikažejo vse vire "
            "iz tega kataloga. Izbira se zapomni.<br>"
            "11. <b>⋯ → Izvozi katalog…</b> shrani izbrane vire v datoteko kataloga (privzeto agis_katalog_izvoz.db).<br>"
            "Hitro okno samo s seznamom virov odpre ikona s tremi pikami v orodni vrstici AGIS."))

        layout.addWidget(self._section_label("Katalogi"))
        layout.addWidget(self._text(
            "<span style='color:#2e7d32'>●</span> <b>Katalog CPA</b> — viri CPA, vidni samo v omrežju CPA.<br>"
            "<b>∴ Katalog AGIS</b> — skupni seznam virov (vedno na vrhu), "
            "ki se ob zagonu prenese z GitHuba (izklop v zavihku <b>Nastavitve</b>).<br>"
            "<span style='color:#ef6c00'>●</span> <b>Moji viri</b> — vaši viri, shranjeni samo v vašem QGIS-u.<br>"
            "Skriti viri so prikazani sivo, ko vklopite <b>⋯ → Pokaži skrite vire</b>. "
            "Katalog AGIS se v vtičniku ne ureja, vzdržuje se na GitHubu."))

        layout.addWidget(self._section_label("Dodajanje in urejanje virov"))
        layout.addWidget(self._text(
            "Urejanje vklopite z gumbom " + EDIT + " <b>Urejanje</b>. Dokler je vklopljeno, je pod iskalnim poljem "
            "<span style='color:#c62828'><b>rdeča črta</b></span>, katalogi, ki jih lahko urejate, pa imajo na gumbu ✎.<br>"
            "• V omrežju CPA vas AGIS ob vklopu enkrat na sejo vpraša za prijavo v bazo CPA. Prijava s pravico "
            "urejanja omogoči urejanje <b>Kataloga CPA</b> (kurator); <b>Samo Moji viri</b> ali prijava brez pravic "
            "omogoči urejanje samo vaših virov. Geslo ni shranjeno; odjava: ⋯ → Odjava iz kataloga CPA.<br>"
            "• Zunaj omrežja CPA se urejanje vklopi takoj, samo za Moji viri.<br><br>"
            "<b>Dodajanje:</b> sloj ali skupino pripravite v QGIS-u (slog, oznake, merila), jo izberite v panelu "
            "<b>Sloji</b>, kliknite " + ADD + ", izpolnite naziv in opis ter izberite katalog. "
            "AGIS pred shranjevanjem odstrani osebna gesla, opozori na lokalne datoteke "
            "in lokalne slike (SVG) vdela v slog, da vir deluje vsem enako.<br>"
            "<b>Desni klik</b> na vir v katalogu, ki ga urejate: <b>Uredi podatke</b>, <b>Zamenjaj z izbranim</b> "
            "(npr. ko se spremeni naslov storitve), <b>Nadomestni vir</b>, <b>Razveljavi zadnjo zamenjavo</b>, "
            "<b>Skrij za vse</b> / <b>Prikaži za vse</b>, <b>Izbriši</b>. Viri, skriti za vse, so med urejanjem "
            "prikazani sivo, da jih lahko spet prikažete."))

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

        layout.addWidget(self._section_label("Delovni sloji (omrežje CPA)"))
        layout.addWidget(self._text(
            "Gumb <b>Naloži delovne sloje</b> v orodni vrstici (viden le v omrežju CPA): enkrat na sejo se "
            "prijavite s svojim uporabnikom, nato se odpre seznam delovnih slojev. Naložite jih z dvojnim "
            "klikom, s povleci-spusti v panel Sloji ali z <b>Naloži vse</b>. Sivi sloji za vašo prijavo niso "
            "dostopni. Slogi in spustni seznami so shranjeni v bazi; tabele, iz katerih berejo spustni seznami, "
            "se naložijo same."))

        layout.addWidget(self._section_label("Nastavitve"))
        layout.addWidget(self._text(
            "Vklop kataloga AGIS, lasten sloj parcel in naslovi spletnih storitev (GURS WFS, "
            "eArheologija, eVRD) – vsak z gumbom <b>↺</b> za privzeti naslov. Spremembe se shranijo takoj."))
        layout.addWidget(self._section_label("Delo od doma (VPN)"))
        layout.addWidget(self._text(
            "AGIS prebere nastavitve CPA z omrežnega diska – privzeto z diska <b>V:</b>, kot v pisarni. "
            "Če diska V: doma nimate, v <b>Nastavitve → Povezave</b> vnesite omrežno pot do datoteke "
            "z nastavitvami (\\\\strežnik\\mapa\\…; dobite jo pri skrbniku AGIS na CPA) ali pa si disk V: "
            "povežite. Če ste prek VPN povezani, a vas Windows še ni "
            "prijavil v omrežni disk (domači računalnik, drug uporabnik), AGIS to pokaže in ponudi gumb "
            "<b>Prijava v omrežni disk</b> (tudi v Nastavitve → Povezave). Odpre se mapa in Windows vpraša "
            "za uporabniško ime in geslo – označite <b>»Zapomni si moje poverilnice«</b>. AGIS nato sam "
            "prebere nastavitve; naslednjič to ni več potrebno. Brez VPN AGIS deluje kot doma, brez baze CPA."))

        layout.addStretch()
        return self._scrollable(w)               