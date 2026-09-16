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
Hap SQL Editor te Supabase dhe ekzekuto `financat_skema.sql`. Krijon 9 tabela
(`fin_*`), indekset dhe cilesimet fillestare. RLS ndizet pa asnje policy:
celesi `anon` nuk lexon dot asgje — vetem backend-i, me service key, shkruan
dhe lexon.

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

### Balanca
`bilanci_fillestar + hyrjet − daljet ± transferet`, per cdo llogari, ne
monedhen e saj; totalet kthehen ne monedhen baze me kurset e `fin_cilesimet`.
Nje monedhe pa kurs numerohet 1:1 **dhe sinjalizohet si alarm** — nuk fshihet.

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
| `POST /api/fin/skenar` | "Po sikur?" — rillogarit pa e prekur bazen |
| `GET/POST /api/fin/te-dhena/{tabela}` | Lexo / shto |
| `PATCH/DELETE /api/fin/te-dhena/{tabela}/{id}` | Ndrysho / fshi |
| `GET/PATCH /api/fin/cilesimet` | Monedha baze, kurset, pragjet |
| `POST /api/fin/keshilltari` | Analize me Claude + kerkim ne internet |
| `POST /api/fin/skano-opsionet` | Skanim tregu per pozicionet dhe borxhet |
| `POST /api/fin/apliko-cmimet` | Zbaton cmimet e propozuara |
| `GET /api/fin/raportet` | Arkivi i analizave |
| `GET /api/fin/shendeti` | Pa token; vetem gjendja e konfigurimit |

Tabelat: `llogarite`, `transaksionet`, `detyrimet`, `planet`, `te-ardhurat`,
`investimet`, `objektivat`, `raportet` (vetem lexim).

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

## 5. Kufijte e njohur

- **Futje me dore.** Nuk lidhet me banka (PSD2/open banking); s'ka API bankare
  shqiptare qe ta beje kete pa licence institucioni pagesash.
- **Kurset jane statike** te `fin_cilesimet`. Perditesohen me dore ose me nje
  skanim; nuk terhiqen automatikisht.
- **Nje perdorues.** Kolona `user_id` ekziston kudo; kalimi ne shume perdorues
  eshte ndryshim auth-i (token → sesion i lidhur me `users`) plus policy RLS,
  jo migrim te dhenash.
- **Projeksioni s'eshte profeci.** Eshte aritmetike mbi ate qe ke futur: te
  dhena te mangeta japin projeksion optimist. Nese `muaj_te_plote < 3`,
  qendrueshmeria merr gjysmen e pikeve pikerisht sepse s'ka ende baze gjykimi.
