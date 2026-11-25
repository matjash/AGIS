![AGIS](https://user-images.githubusercontent.com/32578708/75514424-bfed1000-59f7-11ea-92fd-25bd466aed83.png)

## AGIS – Arheološki GIS

Vtičnik za QGIS (3.28 ali novejši, tudi QGIS 4), ki arheologom in drugim pomaga hitro postaviti GIS projekt
za območje Republike Slovenije. Razvit je v okviru Centra za preventivno arheologijo (CPA), ZVKDS.

### Kaj omogoča

- **Naloži sloje** – seznam pripravljenih virov (ortofoto, kataster, lidar, evidence dediščine …) z enakim
  slogom za vse. Iskanje po nazivu, opisu in oznakah; nalaganje z dvojnim klikom ali s povleci-spusti v panel
  Sloji. Viri so v treh katalogih:
  - **Katalog AGIS** – skupni seznam, objavljen v tem repozitoriju (`catalogue/agis_katalog.db`),
  - **Katalog CPA** – viri CPA, vidni v omrežju CPA,
  - **Moji viri** – vaši lastni viri.
- **Parcele** – iskanje parcele po K.O. in številki, parcele pod slojem (z odmikom) in seznam parcel kot
  besedilo. Vir: kopija katastra v bazi CPA, GURS WFS ali lasten sloj.
- **eArheologija** in **eVRD** – iskanje po arheoloških raziskavah in registru nepremične kulturne dediščine
  (kopija v bazi CPA ali geohub.gov.si).
- Ikona s tremi pikami v orodni vrstici odpre majhno okno samo za nalaganje slojev.

Navodila so v vtičniku, zavihek **Pomoč**.

### Namestitev

QGIS → Vtičniki → Upravljanje in namestitev vtičnikov → poiščite **AGIS**.

### Za razvijalce

Mapa `dev/` ni del repozitorija (je v `.gitignore`), ker vsebuje krajevne nastavitve za testiranje; razvijalec jo ima samo na svojem računalniku.

- `dev/make_zip.py` – zip za plugins.qgis.org (brez mape `dev/`).
- `dev/agis_dev.py` – preklop na lokalno kopijo baze CPA (`use_local()`, `use_production()`).
- `dev/cpa_catalogue.sql` – shema `agis` in tabela kataloga `agis.agis_viri` v bazi CPA.
- `dev/agis_nastavitve.ini` – vzorec nastavitev organizacije (strežnik in prijava v bazo, imena tabel). Prava
  datoteka je na omrežnem disku CPA. Privzeta pot (`config.py` → `settings_file`) je pot na disku `V:`, brez imena
  strežnika; kdor diska `V:` nima (npr. prek VPN), vnese omrežno pot v Nastavitve → Povezave. Strežnik in geslo
  zato nista v javni kodi.
- `dev/TESTIRANJE.md` – kontrolni seznam za ročno testiranje.

Napake in predlogi: [Issues](https://github.com/matjash/AGIS/issues).
