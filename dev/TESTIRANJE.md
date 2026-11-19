# AGIS 2.0 – kontrolni seznam za testiranje

Ročno testiranje v pravem QGIS (3.28+ in QGIS 4) z lokalno kopijo baze CPA, GURS WFS in geohubom.

## 0. Priprava
- [ ] Za testiranje z lokalno kopijo baze namesti **mapo repozitorija** (z mapo `dev/`): razpakiraj `agis-2.0-repo.zip` v
      `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\` (nastane mapa `agis`) in ponovno zaženi QGIS.
      `agis-2.0.0.zip` je izdaja brez `dev/` – z njo preveri samo še namestitev prek »Namesti iz ZIP« (QGIS 3.28+ in QGIS 4).
- [ ] Na lokalni kopiji `CPA_Analiza` poženi `dev/cpa_catalogue.sql` (v zadnji vrstici zamenjaj `CPA_admin` s svojo vlogo).
- [ ] Priporočeno: `CREATE INDEX ON public."ZKN parcele" (sifko, parcela);`
- [ ] Python konzola:
      `from agis.dev import agis_dev as d; d.use_local()` (localhost:5433/CPA_Analiza), nato ↺ v panelu.

## A. Osnova
- [ ] QGIS se zažene brez napak, panel AGIS se odpre; po posodobitvi vtičnika ni podvojene orodne vrstice.
- [ ] Oranžna oznaka »DEV: localhost« nad zavihki (brez nje ni prazne vrstice); zavihek **Nastavitve** se odpre takoj (»Baza CPA: preverjam…«, nato »dosegljiva«) in razvojne nastavitve.
- [ ] Zavihki: Naloži sloje, Parcele, eArheologija, eVRD, Nastavitve, Pomoč.
- [ ] Gumb »Naloži delovne sloje« je viden. `d.use_production()` + ↺ → gumb izgine, oznaka DEV izgine.
- [ ] Orodna vrstica: ni več Arcanuma; ikona s tremi pikami odpre majhno okno »AGIS – naloži sloje« (iskanje, dvojni klik, povleci-spusti, desni klik samo Naloži); položaj okna si zapomni.

## B. Katalog virov (zavihek Naloži sloje)
- [ ] **+** z izbranim WMS slojem → Moji viri (oranžno); z izbrano skupino → ena vrstica, nasvet »skupina, N slojev«.
- [ ] **Katalog AGIS** (ikona s tremi pikami) je vedno na vrhu, nato CPA, nato Moji viri. Desni klik nima več »Pokaži skrite« in »Izvozi« (sta v ⋯).
- [ ] Dvojni klik naloži z enakim slogom; več izbranih + desni klik → Naloži; ✕ prekine.
- [ ] Položaj: brez izbire v panelu Sloji → na vrh; izbran sloj → nad njim; izbrana skupina → na vrh skupine; več virov ostane v vrstnem redu.
- [ ] **Povleci-spusti** vrstico (ali več) v panel Sloji: na sloj (zgornja/spodnja polovica → nad/pod), na skupino (v skupino), v prazen prostor (na konec). Spusti drugam (karta) → nič se ne zgodi.
- [ ] Obrazec + ima polje **Oznake** (presledek ali vejica; shrani se kot »a, b, c«), iskanje najde vir po oznaki; v nasvetu ni več »Posodobljeno«. Obrazec + nima več polja »Vidnost«; Izvozi kot katalog… ima vnaprej označene uradne in moje (ne CPA).
- [ ] Desni klik: Uredi podatke, Zamenjaj z izbranim, Razveljavi zadnjo zamenjavo (dvakrat = nazaj), Skrij, ⋯ → Pokaži skrite vire, Prikaži, Izbriši.
- [ ] **CPA** (zeleno): + → »Katalog CPA« → prijava s tvojim uporabnikom; napačno geslo → jasno sporočilo brez gesla; uporabnik brez pravic → »nima pravice urejati«.
- [ ] Preverjanja ob shranjevanju:
  - [ ] sloj iz baze CPA s tvojo osebno prijavo → v katalogu je javni račun `cpa` (opozorilo)
  - [ ] sloj s shranjeno prijavo QGIS (authcfg) → zavrnjen
  - [ ] lokalni GPKG/SHP → opozorilo »lokalna datoteka«
  - [ ] sloj z lastnim SVG znakom → po nalaganju na drugem računalniku je znak viden
- [ ] Kopiraj v Moji viri (iz CPA) → nova oranžna vrstica.
- [ ] ⋯ → Izvozi kot katalog… → datoteka; `d.set_value("official_catalogue_url", "file:///C:/pot/agis_viri.db")` + ↺ → modre vrstice.
- [ ] Nastavitve → izklopi katalog AGIS → njegove vrstice izginejo takoj, v vrstici stanja »katalog AGIS izklopljen«.
- [ ] Na lokalni kopiji CPA ponovno poženi `dev/cpa_catalogue.sql` (doda stolpec `oznake`); brez tega katalog CPA deluje, oznake se ne shranijo.

## C. Parcele
- [ ] K.O. po šifri, »šifra - ime« in imenu; ime, ki ni enolično → ponudi izbiro.
- [ ] Po izbiri K.O. se ponudijo številke parcel.
- [ ] Obstoječa parcela → Poišči približa in utripne; vrstica »Vir: lokalna kopija KN (28. 2. 2024)«.
- [ ] Naloži kot sloj → začasni sloj; Lastnosti → Metapodatki: »Pridobljeno …, vir …«.
- [ ] Parcela, nastala po 28. 2. 2024 → »Vir: GURS WFS«. **To je prvi pravi preizkus GURS WFS (v testih je bil simuliran).**
- [ ] Neobstoječa parcela → »Parcela ne obstaja. Vir: GURS WFS«.
- [ ] Brez baze CPA (`d.use_production()` doma) → iskanje gre na GURS.
- [ ] Podzavihka »Iskanje parcele« in »Parcele pod slojem«.
- [ ] Na tvoji kopiji CPA: po izbiri K.O. se ponudijo številke parcel; parcele pod slojem se spreminjajo z odmikom in slojem (ime sloja vsebuje odmik).
- [ ] Parcela »'« ali »abc« → »… ni številka parcele«; dolga napaka ne razširi panela, besedilo stanja se da označiti in kopirati.
- [ ] Parcele pod slojem: cel sloj, samo izbrani, z odmikom; preverjeno tudi z GURS (brez CPA) – velika območja → sporočilo o preveliki površini.
- [ ] Negativen odmik (npr. −5 m) → manj parcel; prevelik negativen odmik → »… od območja ne ostane nič«.
- [ ] **Izpiši seznam parcel** → okno z besedilom (vsaka K.O. v svoji vrstici, »in« pred zadnjo, »vse k. o.« / »k. o.«, `;` na koncu vrstic razen zadnje); **Kopiraj** → prilepi v Word.
- [ ] Lasten sloj v zavihku Nastavitve (GPKG/SHP/tabela v bazi; polja se uganejo, shrani se takoj); začasni sloj → opozorilo. Nov prazen projekt (sloj ni naložen) → iskanje še vedno najde v lastnem sloju. ✕ ga pozabi.
- [ ] Lasten sloj z ID K.O. kot besedilom z vodilnimi ničlami (npr. »0505«) → najde.
- [ ] Brez CPA in brez interneta → najde v lastnem sloju; »Uporabi pred ostalimi viri«.

## D. eArheologija in eVRD
- [ ] QGIS se zažene hitro; podatki se naložijo šele ob odprtju zavihka (»Prikazanih X od Y · vir: …«).
- [ ] Na kopiji CPA brez pogledov `public.mk_arheo_vrste_arh_raziskav` / `public.mk_evrd` → »vir: geohub«. Ko pogled obstaja → »vir: baza CPA, kopija …« (datum iz komentarja pogleda).
- [ ] eArheologija: podzavihka »Zaključene raziskave« in »Raziskave v teku«; stolpci Koda (stalna širina za kodo kot 76-2344), Raziskovalni postopek in Izvajalec si delita ostalo 70 / 30; brez vodoravnega drsnika; besedilo v dveh vrsticah, celotno v nasvetu.
- [ ] Desni klik (zaključene): Več informacij (dolgo besedilo se prelomi, povezave delujejo), Pokaži geometrijo, Odpri poročilo 1 / 2 (le če obstajata). Pri »v teku« ni poročil.
- [ ] eVRD: stolpci EID, Ime, Režim, Tip; ~32 000 zapisov se naloži v razumnem času; desni klik → Podrobnosti, Pokaži geometrijo.
- [ ] Razvrsti po stolpcu → dvojni klik približa pravi zapis.
- [ ] »Le v obsegu karte« vklop/izklop, premik karte osveži seznam; »Polja« – iskanje samo po izbranih poljih.
- [ ] Projekt v drugem CRS (npr. EPSG:3857) – približanje in obseg delujeta.
- [ ] Nastavitve → Spletni viri: spremeni naslov eVRD na FeatureServer (`…/MK_EVRD/FeatureServer/0`, če obstaja) → po ponovnem zagonu QGIS deluje; ↺ vrne privzeto. Oznaka DEV se ne pojavi.

## E. Delovni sloji (2.0.1)
- [ ] Gumb »Naloži delovne sloje« → prijava (uporabniško ime je izpolnjeno od zadnjič). Napačno geslo → eno sporočilo, brez ponavljajočih oken za geslo.
- [ ] Po prijavi se odpre okno »AGIS – delovni sloji«: seznam brez vrstic »admin«; sloji brez pravic so sivi (nasvet pove zakaj). Ponoven klik na gumb odpre okno brez nove prijave.
- [ ] Dvojni klik / desni klik → Naloži: nad izbrani sloj oz. v izbrano skupino, brez izbire na vrh. Povleci-spusti v panel Sloji. Sloj, ki je že v projektu, se ne naloži dvakrat.
- [ ] »Naloži vse« → skupina »Delovni sloji« na vrhu, vsi berljivi sloji.
- [ ] Slog iz baze (privzeti slog v `layer_styles`) se uporabi.
- [ ] **ZLS Interpretacija_delovno**: polje Vrsta je spustni seznam iz `ZLS interpretacija_kategorije`, samo vrste za izbrani Sloj; tabela kategorij se naloži sama, poleg sloja.
- [ ] Gumb z uporabnikom (👤) → prijava z drugim uporabnikom, seznam se osveži.
- [ ] Shrani projekt z delovnimi sloji, zapri QGIS, odpri projekt (QGIS lahko vpraša za geslo – Prekliči), nato »Naloži delovne sloje« in prijava → »Ponovno povezanih delovnih slojev …«, sloji spet delujejo.
- [ ] Sloji ostanejo berljivi čez nekaj minut (premik karte, tabela atributov, urejanje). Po zaprtju QGIS v Nastavitve → Možnosti → Overjanje ni več prijave »AGIS začasno (…)«.
- [ ] »Odstrani delovne sloje« → skupina in delovni sloji (tudi tabela kategorij) izginejo.
## F. QGIS 4
- [ ] Vsi zavihki, okna (+ obrazec, prijava, izvoz, seznam parcel, delovni sloji) se odprejo brez napak (Vtičniki → Python konzola za morebitne napake, Dnevnik sporočil → AGIS).

## G. Pred izdajo
- [ ] Na produkciji: `cpa_fix_privileges.sql` (najprej ROLLBACK, nato COMMIT), `dev/cpa_catalogue.sql`, indeks na `"ZKN parcele"`.
- [ ] Ko bo replikator: pogleda `public.mk_arheo_vrste_arh_raziskav` in `public.mk_evrd` (imena stolpcev kot na geohubu, stolpec `objectid`, komentar »Datum zadnje posodobitve: …«, `GRANT SELECT … TO cpa`), npr.
      `CREATE VIEW public.mk_evrd AS SELECT * FROM replikator.mk_evrd; COMMENT ON VIEW public.mk_evrd IS 'Datum zadnje posodobitve: 2026-11-18'; GRANT SELECT ON public.mk_evrd TO cpa;`
- [ ] Uradni katalog napolnjen, izvožen in commitan kot `catalogue/agis_viri.db`.
- [ ] Različica v `metadata.txt` (če je 2.0.0 že na plugins.qgis.org → 2.0.1).
- [ ] `d.use_production()`; `python dev/make_zip.py` → zip za plugins.qgis.org.
