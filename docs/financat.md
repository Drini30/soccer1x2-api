# Financat — moduli personal i kontrollit financiar

Nje sistem i vetem per gjendjen tende financiare: balanca, borxhe, arketime qe
priten, shpenzime urgjente dhe te planifikuara, investime, objektiva — dhe mbi
te gjitha keto, nje skor sjelljeje, nje projeksion 12-mujor dhe nje keshilltar
qe kerkon ne internet per opsionet qe kane lidhje me ate qe ke shtuar.

Rri ne te njejtin repo dhe te njejtin proces me SOCCER1X2, por eshte produkt
krejt tjeter: kod i vecuar ne `financat.py`, tabela me prefiks `fin_`, token
te vetin. Nese moduli deshton, API-ja e parashikimeve nis njesoj.

---

## 1. Ngritja

### a) Baza e te dhenave
Hap SQL Editor te Supabase dhe ekzekuto, me kete radhe:

1. `financat_skema.sql` — 9 tabelat (`fin_*`), indekset, cilesimet fillestare.
2. `financat_migrim_2.sql` — datat e pagesave, lidhja e transaksionit me
   burimin e te ardhurave, kursi i LEK-ut. I sigurt te ri-ekzekutohet.
3. `financat_migrim_3.sql` — shuma mujore behet opsionale, dritarja e dates
   ("18-20"), muaji i shpenzimeve vjetore, llogaria "Kesh".
4. `financat_migrim_4.sql` — bizneset: pasqyra e fitimit, zerat, pika e
   barazimit, lidhja e transaksioneve me biznesin.
5. `financat_migrim_5.sql` — buxhetet mujore per kategori.

RLS ndizet pa asnje policy: celesi `anon` nuk lexon dot asgje — vetem
backend-i, me service key, shkruan dhe lexon.

### b) Variablat e mjedisit (Render → Environment)

| Variabli | I detyrueshem | Cfare ben |
|---|---|---|
| `FIN_TOKEN` | **Po** | Token-i i aksesit. Pa te, i gjithe moduli kthen 503 — i mbyllur, jo i hapur. Gjenero nje te rastesishem: `openssl rand -hex 24`. |
| `SUPABASE_SERVICE_KEY` | Po | Ekziston tashme per SOCCER1X2; riperdoret. |
| `ANTHROPIC_API_KEY` | Jo | Pa te punon gjithcka pervec Keshilltarit. |
| `FIN_MODELI` | Jo | Parazgjedhje `claude-opus-5`. |
| `FIN_USER_ID` | Jo | Parazgjedhje `une`. |

### c) Perdorimi
Hap `https://<domeni>/financat`, fut `FIN_TOKEN`-in. Ruhet ne `localStorage`
te shfletuesit tend dhe dergohet si header `X-Fin-Token` ne cdo kerkese.

---

## 2. Si mendon motori

Ndarja eshte e rrepte: **numrat i nxjerr kodi, jo modeli gjuhesor.** Claude
merr numra te gatshem dhe sjell vetem ate qe kodi nuk e di — normat e sotme,
cmimet, opsionet e tregut.

### Balanca dhe monedhat
`bilanci_fillestar + hyrjet − daljet ± transferet`, per cdo llogari, ne
monedhen e saj; totalet kthehen ne monedhen baze me kurset e `fin_cilesimet`.
Nje monedhe pa kurs numerohet 1:1 **dhe sinjalizohet si alarm** — nuk fshihet.

`LEK`, `LEKE`, `LEKË` dhe `L` njihen si e njejta monedhe me kodin standard
`ALL`. Monedha baze ndryshohet nga Menu → Cilesimet; kurset rillogariten vete
ndaj saj (nese 1 LEK ishte 0.0102 EUR, kalimi ne LEK e ben 1 EUR = 98.04 LEK).

### Shpenzimi mujor i pritshem
```
shpenzimi = baza + planet e perseritshme + kestet e borxheve
```
`baza` = mesatarja e daljeve te 6 muajve te fundit te plote **duke perjashtuar**
transaksionet e lidhura me nje plan (`plani_id`) ose me nje detyrim
(`detyrimi_id`). Keshtu nje kest qe e ke regjistruar si transaksion nuk
numerohet dy here — nje here si shpenzim historik, nje here si kest.
Muaji rrjedhes nuk hyn ne mesatare sepse eshte i paplote.

### Projeksioni
Simulim muaj pas muaji i bilancit likuid, per 1-60 muaj:
- te ardhurat e deklaruara + planet me drejtim `hyrje`;
- arketimet **e peshuara me sigurine** (800 € me siguri 70% = 560 €), te
  numeruara vetem nje here, ne muajin e afatit; ato qe e kane kaluar afatin
  bien ne muajin e pare;
- daljet: baza + planet (te shumezuara me `probabiliteti`);
- borxhet amortizohen realisht — interesi mujor mbi mbetjen, pastaj kesti. Nje
  borxh pa kest por me afat shlyhet i teri ne muajin e afatit.

### Skori i sjelljes (0-100)
| Perberesi | Pike | Matet me |
|---|---|---|
| Norma e kursimit | 25 | `(te ardhura − shpenzim) / te ardhura` ndaj synimit |
| Rezerva e emergjences | 20 | `likuiditet / shpenzim mujor` ndaj `rezerva_muaj` |
| Barra e borxhit | 20 | DTI: kestet / te ardhurat (≤10% plot, ≥50% zero) |
| Qendrueshmeria | 15 | Koeficienti i variacionit i daljeve mujore |
| Disiplina e afateve | 10 | Sa detyrime/arketime e kane kaluar afatin |
| Struktura e te ardhurave | 10 | Diversifikimi + pjesa pasive |

Nivelet: <30 Kritik · <50 Brishte · <70 Stabil · <85 I forte · ≥85 Elitar.
Cdo perberes kthen vleren, synimin dhe shpjegimin — nese skori bie, e sheh
saktesisht ku ra.

### Kapaciteti
Sa peshe mban vertet: teprica e lire mbi rezerven, rrjedha neto mujore, dhe
kesti maksimal i nje detyrimi te ri (60% e rrjedhes neto, dhe njekohesisht
DTI total ≤35% — kthehet edhe cili nga te dy kufijte po te ndalon).

### Shpenzimet fikse
Ne regjistri ka dy pamje te vecanta mbi te njejten tabele `fin_planet`:

- **Shpenzime mujore fikse** — qeraja, kredia, interneti, telefoni, kopshti.
  Ruhen me `frekuenca = mujore`, `drejtimi = dalje`.
- **Shpenzime vjetore fikse** — taksa e tokes/shtepise/makines, siguracionet,
  kontrolli teknik. Ruhen me `frekuenca = vjetore` dhe kerkojne
  `muaji_pageses`: pa te, nje shpenzim vjetor s'ka kur te kujtohet.

Krahas tyre, **Shpenzime ditore** eshte nje pamje mbi `fin_transaksionet`
(vetem daljet) me kategori te gatshme — ushqime, karburant, kafe, veshje,
farmaci. Keto jane shpenzimet e ndryshueshme, dhe pikerisht ato formojne
"bazen" e shpenzimit mujor dhe qendrueshmerine ne skor.

Cdo liste kategorish ka "+ Shkruaj vete": asnje liste s'i mbulon te gjitha.

Nuk eshte tabele e trete — jane filtra mbi te njejten strukture, ndaj
projeksioni dhe shpenzimi mujor i pritshem i marrin parasysh njesoj.

### Dita e pageses mund te jete nje dritare
`dita_pageses` + `dita_pageses_fund` shkruhen ne nje fushe te vetme:
`18` ose `18-20`. Vonesa numerohet nga dita e **fundit** e dritares — perndryshe
nje page qe pritet mes 18-es dhe 20-es do te dilte "e vonuar" me 19.

### Shkallet 1-5 — nga cila ane nisin
Numri ruhet ne baze, por ne ekran del me emrin e vet. Kahjet:

| Fusha | 1 do te thote | 5 do te thote |
|---|---|---|
| `prioriteti` (borxhe, objektiva) | **jetik**, nuk shtyhet dot | shtyhet pa pasoje |
| `domosdoshmeria` (plane, shpenzime) | **e domosdoshme** (buke, qira) | luks i paster |
| `siguria` (te ardhurat) | shume e pasigurt | **e garantuar** (kontrate) |
| `rreziku` (investimet) | **shume i sigurt** (depozite) | spekulativ |

Dy te parat nisin nga 1 sepse "prioriteti 1" eshte menyra e zakonshme e te
thenit "i pari ne rradhe". Dy te fundit nisin nga 5 sepse aty numri i larte
matet si cilesi — siguri me shume, rrezik me shume.

`siguria` te detyrimet eshte gje tjeter: perqindje 0-100, sa nga ai arketim
e pret vertet.

### Njoftimet e pagesave
Nje pagese e perseritshme (page, qira, kest freelance) njihet **e kryer** kur
ekziston nje transaksion i lidhur me ate burim (`te_ardhura_id` ose
`plani_id`) brenda atij muaji. Pa ate lidhje sistemi s'do ta dinte dot nese
pagesa u shenua apo jo.

Rregullat:
- Njoftimi shfaqet tre dite para dates, jo me heret — me heret eshte zhurme.
- Kontrollohen dy muaj (ai rrjedhes dhe ai i shkuar), qe nje page e harruar
  ne fund te muajit te mos zhduket nga ekrani me 1 te muajit tjeter.
- Nuk pyetet kurre per nje muaj kur burimi ende s'ekzistonte (`krijuar_me`).
- `shuma_e_ndryshueshme = true` (tipike per freelance) → njoftimi te pyet
  "sa more kete muaj?" dhe e le shumen bosh. Ne te kundert e propozon vete.
- Nje burim me `shuma_mujore` bosh nuk numerohet zero: vlera nxirret nga
  mesatarja e muajve me pagese te shenuar (6 muajt e fundit), dhe njoftimi e
  tregon ate mesatare si orientim pa e mbushur fushen.
- Klikimi i njoftimit hap formularin e gatshem; ruajtja krijon transaksionin
  dhe njoftimi hesht.

### Bizneset
Nje biznes mbahet **njesi me vete**, jo kategori shpenzimesh. Arsyeja eshte
praktike dhe e njohur: me para te perziera nuk kuptohet dot nese biznesi ecen.
Ura e vetme mes tij dhe teje eshte **terheqja** — dhe vetem ajo shfaqet si e
ardhur personale, pasi ta shenosh.

Cdo transaksion me `biznesi_id` **perjashtohet** nga shpenzimet personale, nga
kategorite dhe nga te ardhurat personale. Bilanci i llogarise vazhdon ta
permbaje (paraja levizi vertet), por analiza personale jo.

Zerat kane tre role:

| Roli | Si llogaritet | Shembull |
|---|---|---|
| `te_ardhur` | `cmimi_njesi × sasia`, ose nje shume e sheshte | 12 € × 40 abonente |
| `kosto_fikse` | shuma, e sjelle ne muaj | Render 25 €/muaj, domain 15 €/vit |
| `kosto_variabile` | `kosto_per_njesi × njesite`, ose `% e te ardhurave` | 0.8 €/abonent, komision 3% |

Pasqyra mujore:
```
te ardhura − kosto variabile = marzhi i kontributit
marzhi − kosto fikse         = fitimi
```

**Pika e barazimit** llogaritet mbi marzhin e kontributit, jo mbi te ardhurat
bruto — perndryshe del gjithmone me e ulet se sa eshte vertet:
`kosto fikse ÷ marzhi%`, e kthyer ne njesi me cmimin mesatar. **Siguria** eshte
sa perqind mund te bien shitjet para se te hyhet ne humbje.

Alarmet e biznesit: humbje, terheqje mbi fitimin ("diferenca del nga kapitali,
jo nga puna"), siguri nen 20%, dhe mungese e te ardhurave te regjistruara.

### Buxhetet mujore
Buxheti eshte gje tjeter nga plani: plani thote *"qeraja eshte 30.000 dhe
paguhet me 5"*; buxheti thote *"ushqimeve u kam vene 35.000 ne muaj dhe deri
sot kam harxhuar 28.000"*. I pari eshte detyrim, i dyti eshte kufi qe e vendos
vete dhe qe mund ta kalosh — por duke e ditur.

Nje shirit qe thote vetem "78% e perdorur" genjen me daten 5 dhe qeteson me
daten 28. Prandaj cdo buxhet krahasohet me **ritmin e pritur**: me 18 shtator
duhen harxhuar rreth 60% e tij. Vija vertikale ne shirit tregon ku duhet te
ishe sot; mbushja tregon ku je vertet.

| Gjendja | Kur |
|---|---|
| `brenda` | nen pragun tend dhe brenda ritmit |
| `afer` | mbi pragun e alarmit (parazgjedhje 85%) |
| `mbi_ritem` | projeksioni i fundit te muajit e kalon buxhetin me mbi 5% |
| `kaluar` | e ka tejkaluar (rreptesisht mbi 100%) |

Nje buxhet i shpikur nga ajri kalohet muajin e pare dhe braktiset te dytin,
ndaj "Propozo nga historiku" i mbush me **medianen** e muajve te fundit — me
sjelljen tende reale. Shpenzimet e biznesit nuk prekin asnje buxhet personal.

### Motori i objektivave
Nje objektiv nuk eshte vetem nje shifer: motori i kthen nje plan.

1. **Sa kerkon ne muaj** = (synimi − arritura) / muajt deri ne afat.
2. **Sa ke** = rrjedha neto mujore, **e zbritur** nga objektivat me prioritet
   me te larte — dy objektiva nuk mund te premtojne te njejtat para. Rendi:
   prioriteti (1 i pari), pastaj afati me i afert.
3. **Nga mund te dalin para**, sipas sigurise:
   - *teprica* — sa e kaloi nje kategori **medianen** e vet muajin e fundit.
     Mediana, jo mesatarja: nje blerje e madhe e nje muaji nuk duhet ta ngreje
     pragun perballe te cilit matet muaji tjeter. Kthimi te mesatarja jote
     nuk eshte sakrifice, eshte korrigjim.
   - *planet qe i ke shenuar vete* me domosdoshmeri 4-5.
   - *shkurtim* — deri ne 30% e nje kategorie jo te domosdoshme.
   Kategorite e domosdoshme (ushqime, qira, kredi, drita, uji, farmaci,
   kopshti, transport…) nuk propozohen kurre: te presesh ushqimin nuk eshte
   kursim, eshte deshtim i planit.
4. **Konfliktet me rendin e prioriteteve** — nuk ndalohet asgje, i thuhet cmimi:
   - rezerve nen nje muaj shpenzime → `ndal`, sepse nje defekt e kthen planin
     ne borxh te ri;
   - borxh me interes ≥ 8% → `kujdes`, me shumen e interesit qe kushton
     vonesa. Shlyerja e atij borxhi eshte kthim i garantuar.
5. **Verdikti**: i arritshem · me sakrifice · duhet shtyre · pa afat, plus
   data realiste e llogaritur nga ritmi i mundshem.

### Strategjia e borxhit
Krahason **ortekun** (interesi me i larte i pari) me **debollen** (borxhi me i
vogel i pari), me te njejten shume shtese, dhe kthen muajt deri ne shlyerje dhe
interesin total per te dyja.

---

## 3. Rrugët

Te gjitha kerkojne `X-Fin-Token`, pervec `/api/fin/shendeti` dhe faqes.

| Rruga | Cfare ben |
|---|---|
| `GET /financat` | Faqja |
| `GET /api/fin/panel?muaj=12` | Gjithcka ne nje thirrje |
| `GET /api/fin/skor` · `/alarmet` · `/projeksion` | Pjese te vecanta |
| `GET /api/fin/njoftimet` | Pagesat e pritshme qe s'jane shenuar |
| `POST /api/fin/llogaria-kesh` | Kthen llogarine "para ne dore", duke e krijuar nese mungon |
| `POST /api/fin/regjistro-pagese` | Mbyll nje njoftim duke krijuar transaksionin |
| `POST /api/fin/skenar` | "Po sikur?" — rillogarit pa e prekur bazen |
| `GET/POST /api/fin/te-dhena/{tabela}` | Lexo / shto |
| `PATCH/DELETE /api/fin/te-dhena/{tabela}/{id}` | Ndrysho / fshi |
| `GET/PATCH /api/fin/cilesimet` | Monedha baze, kurset, pragjet |
| `POST /api/fin/keshilltari` | Analize me Claude + kerkim ne internet |
| `POST /api/fin/skano-opsionet` | Skanim tregu per pozicionet dhe borxhet |
| `POST /api/fin/apliko-cmimet` | Zbaton cmimet e propozuara |
| `GET /api/fin/raportet` | Arkivi i analizave |
| `POST /api/fin/buxhete-nga-historiku` | Krijon buxhete nga mediana e kategorive |
| `GET /api/fin/eksport` | Gjithcka ne nje JSON te vetem |
| `GET /api/fin/eksport/{tabela}.csv` | Nje tabele si CSV |
| `GET /api/fin/shendeti` | Pa token; vetem gjendja e konfigurimit |

Tabelat: `llogarite`, `transaksionet`, `detyrimet`, `planet`, `te-ardhurat`,
`investimet`, `objektivat`, `raportet` (vetem lexim). Listimi pranon filtrat
`frekuenca`, `drejtimi`, `lloji`, `biznesi_id` — mbi ta ndertohen pamjet e
shpenzimeve fikse dhe ato te bizneseve. Tabelat e bizneseve: `bizneset` dhe
`zerat-e-biznesit`.

Shkrimi filtrohet me liste te bardhe fushash — `id`, `user_id` dhe
`krijuar_me` nuk vendosen dot nga jashte, dhe cdo PATCH/DELETE kufizohet me
`user_id`.

---

## 4. Keshilltari dhe privatesia

Gjendja jote financiare i dergohet API-t te Anthropic **vetem kur e shtyp vete
butonin** — asgje nuk niset ne sfond, asnje cron. Dergohet fotografia e
llogaritur (shuma, afate, emra palesh, simbole), jo transaksionet e papërpunuara.
Cdo analize ruhet ne `fin_raportet` bashke me burimet e cituara.

Cmimet e gjetura ne internet **nuk hyjne automatikisht ne baze**: kthehen si
propozime dhe zbatohen vetem me `/apliko-cmimet`. Nje cmim i gabuar nga nje faqe
e rastesishme nuk duhet te te ndryshoje neto vleren pa e pare ti.

Keshilltari nuk eshte keshilltar i licencuar investimesh. Interpreton numrat e
tu dhe sjell fakte tregu me burim; vendimin e merr ti.

---

## 4b. Kopja e sigurt
Nje aplikacion qe mban gjithe jeten tende financiare duhet te te lejoje ta
marresh ate jashte tij — pa kete, cdo gabim imi ose i Supabase-it do te ishte
humbje e perhershme.

- **Menu → Ruaj kopje (JSON)** shkarkon gjithcka ne nje skedar te vetem.
- **Shkarko CSV** ne cdo tabele te regjistrit e jep ate tabele per Excel.

Token-i udheton si header, ndaj shkarkimi behet me `fetch` dhe nje blob — nje
link i thjeshte do te merrte 401.

## 5. Kufijte e njohur

- **Futje me dore.** Nuk lidhet me banka (PSD2/open banking); s'ka API bankare
  shqiptare qe ta beje kete pa licence institucioni pagesash.
- **Kurset jane statike** te `fin_cilesimet`. Ndryshohen nga Menu → Cilesimet
  ose nga nje skanim; nuk terhiqen automatikisht nga tregu.
- **Nje perdorues.** Kolona `user_id` ekziston kudo; kalimi ne shume perdorues
  eshte ndryshim auth-i (token → sesion i lidhur me `users`) plus policy RLS,
  jo migrim te dhenash.
- **Projeksioni s'eshte profeci.** Eshte aritmetike mbi ate qe ke futur: te
  dhena te mangeta japin projeksion optimist. Nese `muaj_te_plote < 3`,
  qendrueshmeria merr gjysmen e pikeve pikerisht sepse s'ka ende baze gjykimi.
