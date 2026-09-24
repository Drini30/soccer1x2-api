# Zinxhiri i llogaritjes — çdo hallkë, çdo vlerë, çdo rol

Gjendja më 24 shtator 2026. Çdo hallkë është aty ku e gjen te `soccer_api.py`,
në funksionin `analizo_ndeshjen_premium_master()` përveç kur shënohet ndryshe.

Tri lloje vlerash:

| shenja | ku vendoset | a ndryshohet pa deploy? |
|---|---|---|
| **A** | autokalibrim (`/api/cron/kalibro` → `model_config`) | po, vetvetiu |
| **K** | `_konf()` — `model_config` → env-var → kod | po, me dorë |
| **E** | vetëm env-var ose kod | jo, kërkon deploy ose restart |

---

## HYRJA — nga kuotat te probabilitetet

**Ç'bën:** Merr tri kuotat 1X2 dhe heq marzhin e bukmejkerit.

```
marzhi  = 1/k1 + 1/kx + 1/k2          (zakonisht 1.05 – 1.08)
p1_real = (1/k1) / marzhi
px_real = (1/kx) / marzhi
p2_real = (1/k2) / marzhi
```

**Roli:** Këto tri numra janë **shtylla kurrizore e gjithë zinxhirit**. Hyjnë te
xG-ja bazë, te moduluesi, te blendi final i 1X2 dhe te moduli i fituesit. Nëse
kuotat mungojnë, ndeshja nuk gjenerohet fare.

---

## HALLKA 1 — lëndët e para

Mblidhen para se të nisë llogaritja.

| burimi | çfarë jep | dysheme kur mungon |
|---|---|---|
| **DNA** (`team_dna_cache`) | `historical_power` (ELO), `clutch_factor`, `volatility_index`, `draw_affinity` | ELO 600, clutch 1.0, vol 15.0, draw 30.0 |
| **Forma** (`merr_formen_reale`) | golat e shënuar/pësuar, ndarë brenda/jashtë, seria e fitoreve, ndeshjet në 14 ditë | mesatare 1.3 |
| **Renditja** | pozicioni, pikët, diferenca e golave | bosh për kupat |
| **Lëndimet** (API-Football) | numri i mungesave për ekip | 0 |

**`_elo_vlen`** — flamur kritik: `True` vetëm kur **të dy** ekipet kanë ELO të
vërtetë nga DNA. `merr_elo_baze` kthen **600 fiks** për çdo ekip jashtë listës
së 21 gjigantëve, dhe krahasimi i dy vlerave 600 nuk mat asgjë.

> **Matje mbi 902 ndeshje:** kur njëra anë kishte 600 të parazgjedhur, hendeku
> mesatar ishte **245** pikë dhe largësia nga tregu **0.239**; kur të dyja ishin
> reale, hendeku **105** dhe largësia **0.139**. Prandaj kur `_elo_vlen=False`,
> pesha e ELO-s bëhet **zero** dhe peshat e tjera rinormalizohen.

---

## HALLKA 2 — xG bazë nga katër burime

`llogarit_xg_te_perparuara()`, rreshti 5198.

**Burimi 1 — forma, me ndarje brenda/jashtë**

```
xg1_forma = ((sulmi_1_brenda + mbrojtja_2_jashtë)/2) × 0.85 + 0.25
```

Ai `×0.85 + 0.25` është tkurrje drejt mesatares — ekipet me formë ekstreme
tërhiqen brenda.

**Burimi 2 — ELO**

```
p1_elo  = 1 / (1 + 10^(−(elo1−elo2)/400))
xg1_elo = 0.10 + p1_elo × 2.90
```

**Burimi 3 — tregu**

```
xg1_market = 0.10 + p1_real × 3.10
```

Në kod të dyja shkruhen si `XG_FLOOR + p × (tavan − XG_FLOOR)`. Tavani i tregut
është **3.2**, i ELO-s **3.0** — tregut i jepet gamë pak më e gjerë.
`XG_FLOOR = 0.10` *(E)*.

**Burimi 4 — baza:** `1.35` gola, mesatarja globale.

**Peshat** *(E — env-var, rinormalizohen automatikisht në shumë 1)*

| pesha | vlera |
|---|---|
| `W_MARKET` | **0.50** |
| `W_FORMA` | 0.25 |
| `W_BASE` | 0.15 |
| `W_ELO` | **0.10** |

> `W_ELO` u ul nga 0.25 në 0.10 mbi 278 ndeshje. Dy prova: korrelacioni i
> hendekut ELO me diferencën reale të golave ishte **0.074** — zhurmë (tregu
> 0.49, xG 0.44); dhe në regres me tregun brenda, ELO-ja kishte **t = −0.50**.

**Avantazhi shtëpiak:** vendasi `×1.12`, mysafiri `×0.95`. Fiks në kod.

---

## HALLKA 3 — hibridi me XGBoost

`llogarit_xg_hybrid()`, rreshti 5330.

Nëse modelet janë të ngarkuara, xG-ja matematike përzihet me parashikimin e
XGBoost-it. **`W_XGB = 0.55`** *(K)* — pra XGBoost peshon pak më shumë se
matematika. Nëse modelet mungojnë, kthehet i pandryshuar dhe `burimi_xg="math"`.

Veçoritë që i jepen: forma, kuotat, **linja e handikapit aziatik**, kuotat O/U,
data. *(AH hyn vetëm këtu — nuk përdoret askund tjetër si kufizim.)*

---

## HALLKA 4 — moduluesi treg/ELO

Vepron **pas** hibridit, mbi xG-në finale.

```
_mod1 = (xg1_market − xg_1) × MOD_K_TREG + (xg1_elo − xg_1) × MOD_K_ELO
xg_1  = xg_1 + clip(_mod1, −0.45, +0.35)
```

| vlera | | |
|---|---|---|
| `MOD_K_TREG` | **0.50** | *E* |
| `MOD_K_ELO` | **0.20** | *E*, bëhet 0 kur `_elo_vlen=False` |
| kufijtë | **−0.45 / +0.35** | *E*, asimetrikë me qëllim |

**Roli:** de-kompresim. xG-ja e përzier është e ngushtë; ky term e tërheq
drejt tregut dhe ELO-s, duke rritur vendosmërinë.

> **Ky është kanali kryesor i ELO-s, jo `W_ELO`.** Për një hendek 400-pikësh
> ky term shton **0.47 gola** supremaci (0.00119/pikë), kundrejt 0.00061/pikë
> që jep pesha te përzierja — pra moduluesi peshon **dyfishin**. Pjerrësia e
> matur mbi 562 ndeshje të gushtit ishte **0.00123/pikë**.

---

## HALLKA 5 — shumëzuesit e DNA-së

Zbatohen me radhë, të gjithë shumëzues:

| kushti | efekti |
|---|---|
| gjithmonë | `xg × clutch_factor` (0.85–1.15) |
| të dy me `draw_affinity > 35` | `xg × 0.90` te të dyja anët |
| `is_derbi` | `xg × 1.10` te të dyja anët |

**`is_derbi`** = `_elo_vlen` **dhe** hendeku ELO ≤ 30. Kushti `_elo_vlen`
u shtua sepse pa të, dy dysheme 600 e bënin kushtin **gjithmonë të vërtetë** —
73 ndeshje (8%) merrnin zgjerim variance pa asnjë arsye.

---

## HALLKA 6 — moduluesi i lodhjes

`llogarit_modulator()`, rreshti 6436.

```
streak_pen = 0.030 × max(0, fitore_rresht − 3)
cong_pen   = 0.035 × max(0, ndeshje_14ditë − 3)
injury_pen = min(0.12, 0.02 × lëndime)
mod        = 1 − min(0.20, streak_pen + cong_pen) − injury_pen
```

Dysheme **0.60**. `INJURY_PEN_PER = 0.02`, `INJURY_PEN_CAP = 0.12` *(E)*.

**Roli:** kthim drejt mesatares pas serive të gjata, plus lodhje dhe mungesa.

Pas kësaj hallke, të dyja xG-të priten brenda **0.30 – 5.00**. Kjo është pika ku
mbaron xG-ja "e ekipit" dhe fillon xG-ja "e ndeshjes".

---

## HALLKA 7 — moduluesi i totalit

Kjo hallkë **nuk e prek drejtimin** — rishkallëzon të dyja anët me të njëjtin
faktor, pra raporti mbetet i paprekur.

```
total_form   = (sulmi_1 + pësimi_2)/2 + (sulmi_2 + pësimi_1)/2
lam_treg     = λ që jep P(Over 2.5) e tregut, nga zgjidhje binare
total_target = 0.50 × total_form + 0.50 × lam_treg
total_i_ri   = total_aktual + 0.70 × (total_target − total_aktual)
```

| vlera | | |
|---|---|---|
| `TOTAL_FORM_MKT_W` | **0.50** | *K* — sa peshon tregu kundrejt formës |
| `TOTAL_K` | **0.70** | *E* — sa e mbyll hendekun |
| `TOTAL_MIN` / `TOTAL_MAX` | **1.20 / 4.50** | *E* |
| `FORCA_CALIB` | **0** (e fikur) | *E* |

---

## HALLKA 8 — normalizimi `XG_NORM`

**Këtu ndahet rruga.** `xg_1`/`xg_2` origjinale vazhdojnë te logimi dhe te
`training_data`; `_xg1_norm`/`_xg2_norm` shkojnë te simulimi.

```
_xg1_norm = A_HOME + B_HOME × xg_1
_xg2_norm = A_AWAY + B_AWAY × xg_2
```

| vlera | kodi | **live sot** *(A)* |
|---|---|---|
| `A_HOME` | 0.08 | **−0.1438** |
| `B_HOME` | 0.87 | **1.1505** |
| `A_AWAY` | −0.02 | **0.2989** |
| `B_AWAY` | 0.97 | **0.8666** |

> Autokalibrimi i rishkroi më 19 shtator dhe **i aplikoi vetë**, pa deploy.
> λ mesatare u ngrit nga ~2.81 në ~2.94. Vlerat e kodit nuk përdoren më.

⚠️ **Pasojë e matur:** `training_data.xg_1` nuk është λ që simulohet. Çdo
analizë që e trajton si të tillë mat gjënë e gabuar — gabim që e kemi bërë.

---

## HALLKA 9 — sinjali i tregut te totali i skorit

Vepron **vetëm** mbi `_xg*_norm`, pra vetëm mbi rrugën e skorit.

```
tot_mkt = λ që pret tregu nga O/U
tot_tgt = 0.50 × tot_model + 0.50 × tot_mkt
faktori = clip(tot_tgt / tot_model, 0.50, 2.00)
```

**`MKT_TOTAL_W = 0.50`** *(E)*. Rishkallëzon të dyja anët njësoj — **drejtimi
mbetet i paprekur**.

> **I matur:** rritja në 1.00 fiton vetëm **0.007 RMSE** mbi 1.72, dhe e
> përkeqëson anshmërinë. 0.50 është aty ku duhet.

**Hallkë motër, e fikur:** `BOOST_MYSAFIR` *(K, **0** si parazgjedhje)*. Kur
mysafiri ka formë më të mirë se vendasi, zhvendos `+b/2` te mysafiri dhe `−b/2`
te vendasi — pra **shumë-zero**, totali mbetet i paprekur, ndryshon vetëm
drejtimi i skorit. E ndezur asnjëherë deri sot.

---

## HALLKA 10 — Monte Carlo

`simulim_monte_carlo_v2()`, rreshti 5987.

**50,000 simulime** *(E)*. Për çdo simulim:

```
σ = xg × 0.18 × kaos_lige          (×1.15 nëse derbi)
xg_virtual = clip(Normal(xg, σ), 0.05, 6.0)
golat = Poisson(xg_virtual)
```

Ai shtresim — Poisson me λ që vetë luhatet — jep **mbi-shpërndarje**, pra bisht
më të trashë se Poisson-i i thjeshtë. `kaos_lige` vjen nga volatiliteti i të dy
ekipeve dhe nga liga.

**Fara** është `sha256(id_ndeshja)` — pra **e njëjta ndeshje jep gjithmonë të
njëjtin rezultat**. Pa rastësi mes rigjenerimeve.

**`DIST_TOP_N = 40`** *(E)* — sa skore ruhen te `dist_gola`. Ishte 15, dhe me 15
ruhej vetëm **89.5%** e probabilitetit: në **9.1%** të ndeshjeve skori real kishte
probabilitet **zero** sepse as nuk ruhej fare, dhe log-loss e ndëshkonte pafund.
Me 40 mbulimi shkon ~99%. **Nuk e ndryshon skorin e publikuar** (ai zgjidhet nga
top-5) — ndryshon vetëm cilësinë e probabiliteteve të ruajtura.

---

## HALLKA 11 — korrigjimi Dixon-Coles

```
H[0,0] ×= 1 − λ1·λ2·ρ
H[0,1] ×= 1 + λ1·ρ
H[1,0] ×= 1 + λ2·ρ
H[1,1] ×= 1 − ρ
```

**`RHO_DC = −0.12`** — fiks në kod.

Prek **vetëm katër qeliza**: 0-0, 0-1, 1-0, 1-1. Korrigjon nën-prodhimin e
barazimeve të ulëta nga Poisson-i i pavarur.

> **Kufi i matur:** mungesa jonë e barazimeve është **+2.24pp** gjithsej, por
> ajo rri kryesisht te **2-2** (+1.51pp) — ku ky korrigjim nuk arrin.

---

## HALLKA 12 — përzgjedhja e kandidatëve dhe `AFF`

Merren **5 skoret më të mundshme** nga matrica, pastaj renditen me:

```
pikët = frekuenca × 1 / (1 + |total_skori − total_pritur| × AFF)
```

**`AFF_FIKS = 0.15`** *(K)*.

**Roli:** ndëshkon skoret larg totalit të pritur. Me λ≈2.8, një `1-1` (total 2)
ndëshkohet kundrejt `2-1` (total 3).

> **I matur:** kjo hallkë **nuk e zgjedh modën**. Moda e λ-ve tona do të ishte
> `1-1` në 46.9% të ndeshjeve; ne publikojmë `1-1` në 19.3% dhe `2-1` në 26.0%.
> Përputhen vetëm në **39.7%**. Dhe kushton **−0.63pp** te skori i saktë.

---

## HALLKA 13 — moduli i fituesit

```
nëse (p_fitues − p_barazim) > pragu  →  skori DETYROHET ta respektojë
ndryshe                              →  barazimi lejohet
```

| vlera | | |
|---|---|---|
| `WINNER_BURIMI` | **1 = tregu** | *K*, 0=MC, 2=treg+korrigjim |
| `WINNER_PRAG_TREG` | **0.12** | *K*, kur burimi është tregu |
| `WINNER_PRAG` | 0.15 | *K*, vetëm pa kuota |

> **Testi mbi 1,343 ndeshje:** tregu e mund MC-në në **9 nga 10 krahasime**
> (5 pragje × 2 matje), 1 barazim, 0 humbje. Kundrejt MC @ 0.10: **+1.64pp
> skor dhe +2.15pp drejtim njëkohësisht.**

Mbrojtje: nëse asnjë nga top-5 s'e plotëson drejtimin, lista mbetet e paprekur.

---

## HALLKA 14 — draw→LEAN

Nëse skori del barazim **dhe** `|xg1 − xg2| ≥ 0.30`, zëvendësohet me skorin
jo-barazim të rrumbullakosur nga xG — **pa +1**, që totali të mos fryhet.

**`PRAG_LEAN = 0.30`** *(E)*. Fiket me 99.

---

## HALLKA 14b — fallback-u "lojë e hapur"

Në kod kjo ekzekutohet **më vonë** (pas HT/FT), por logjikisht është korrigjim
skori, ndaj rri këtu.

```
nëse (gola_skori ≤ 1) DHE (_xg1_norm + _xg2_norm > FALLBACK_HAPUR):
    kërko te frekuencat skorin më të mirë me total ≥ 2 që respekton
    drejtimin e modulit të fituesit
```

**`FALLBACK_HAPUR = 3.20`** *(K)*. Fiket me 99.

**Roli:** pengon që një ndeshje ku modeli pret vërtet shumë gola të dalë `1-0`
ose `0-0` thjesht sepse ajo qelizë është më e dendura.

> **Dy defekte të ndrequra këtu (korrik 2026):** (1) krahasohej me `xg_1+xg_2`
> **të panormalizuara** ndërsa simulimi punon me totalin e normalizuar; (2) pragu
> ishte **2.5**, nën mesataren reale të golave (2.61) — pra "lojë e hapur"
> përkufizohej si "ndeshje mesatare". Pasoja mbi 329 parashikime: **0 × `0-0`**
> (25 reale) dhe **1 × `1-0`** (40 reale). Degë që gëlltiste çdo skor të ulët dhe
> anulonte krejt efektin e `AFF`-së.
>
> Edhe drejtimi këtu kalon nga `_moduli_i_fituesit` — përpara e mbante testin e
> vet mbi 1X2 tashmë të blenduar me tregun, ndaj mund ta kthente skorin në një
> drejtim që moduli nuk e kishte zgjedhur.

---

## HALLKA 15 — clean-sheet → X-1

**E FIKUR.** `CS_LEAN_XG = 99`.

---

## HALLKA 16 — blendi final i 1X2

**Pas** simulimit, prek **vetëm** probabilitetet 1X2 dhe shanset e dyfishta.
Matrica, skori, O/U dhe GG/NG mbeten **tërësisht të modelit**.

```
p1_final = 0.65 × p1_mc + 0.35 × p1_real
```

**`W_MKT_FINAL = 0.35`** *(K)*.

> **Prova:** log-loss i modelit **1.0095** kundrejt **0.9760** të tregut mbi 258
> ndeshje, **t = 2.33, p = 0.020**.

---

## HALLKA 17 — HT/FT, simulim i pavarur

`simulim_ht_ft_mc()` — **40,000 simulime**, gjysma e parë dhe e dytë veçmas.
HT **nuk** derivohet nga FT.

```
xg_ht = frac_ht × xg_norm        (frac_ht ≈ 0.44, nga XGBoost)
xg_2h = xg_norm − xg_ht
```

> **I matur:** HT/FT me 9 qeliza ka **+5.2pp aftësi** mbi bazën "gjithmonë 1/1",
> **z = +4.69**, në të tre muajt. Por publikojmë vetëm `1/1` (65.9%) dhe `2/2`
> (33.1%) — dy qeliza mbulojnë **99%**, dhe kthimet (`1/2`, `2/1`) nuk i kemi
> thënë **asnjëherë** në 1,538 ndeshje.
>
> **Skori HT veçmas është pa vlerë:** `0-0` në 77% të rasteve, aftësi
> **+0.59pp** mbi rregullin trivial "thuaj gjithmonë 0-0".

---

## HALLKA 18 — kalibrimi Platt

```
p_kalibruar = 1 / (1 + e^(−(A + B × logit(p))))
```

**`PLATT_A = 0.0687`, `PLATT_B = 0.7707`** *(A)*.

`B < 1` do të thotë **tkurrje drejt 50%** — modeli ishte tepër i sigurt.

---

## HALLKA 19 — `best_bet`

`_best_bet_value()`, rreshti 5527.

```
aftësia = p_kalibruar − norma_bazë(tregu)
kandidatët = ata me aftësi ≥ EDGE_MIN DHE p ≥ 0.50
nëse ka  → merr atë me value = p × kuota më të lartë
ndryshe  → merr atë me aftësi më të lartë   ← rezerva
```

**`EDGE_MIN = 0.04`** *(K)*. Normat bazë `BAZE_*` janë *(A)*.

> Rezerva ndizet në **0.2%** të rasteve (3 nga 1,576) — pra praktikisht kurrë.
> Brezat me aftësi të ruajtur e mbajnë premtimin (+2.4pp deri +4.4pp); rreshtat
> e vjetër pa `aftesia` dalin **−10.8pp**, gjë që tregon se `EDGE_MIN` ndreqi
> një defekt të vërtetë.

---

## HALLKA 20 — besueshmëria

Konsensus mes modelit dhe tregut, plus forma. `BES_W_SINJAL = 0.75`,
`BES_W_FORMA = 0.25` *(E)*.

---

## HALLKA 21 — filtri PPM

`_gjenero_pf()`, rreshti 4103. **Jashtë zinxhirit** — zgjedh cilat ndeshje
publikohen si premium.

1. Renditja mbi **gjithë ditën**, edhe ndeshjet e mbaruara
2. Vendi caktohet **një herë**; asgjë jashtë top-10 s'bëhet premium
3. Gatishmëria me **raport** (90% e rreshtave me koeficient), jo numër

`PPM_MAKS_DITE = 10`, `PPM_GATI_RAPORT = 0.90` *(E)*.

---

# Ç'prek çfarë

| hallka | totali | drejtimi | **hendeku** |
|---|---|---|---|
| xG bazë | ✓ | ✓ | ✓ |
| hibridi XGB | ✓ | ✓ | ✓ |
| moduluesi treg/ELO | ✓ | ✓ | **✓ kryesori** |
| DNA / lodhja | ✓ | — | — |
| moduluesi i totalit | **✓** | — | — |
| `XG_NORM` | ✓ | pak | pak |
| tregu te totali | **✓** | — | — |
| Dixon-Coles | pak | — | — |
| `AFF` | zgjedhje | — | — |
| moduli i fituesit | — | **✓** | — |
| draw→LEAN | — | ✓ | — |
| fallback "lojë e hapur" | ✓ (vetëm lart) | ✓ | — |
| blendi 1X2 | — | ✓ (vetëm shfaqja) | — |

**Totali ka pesë hallka. Drejtimi ka katër. Hendeku ka një të vetme të
qëllimshme** — moduluesin treg/ELO. Dhe ajo e vetmja punon mbi ELO-n, jo mbi
diçka që e dallon këtë ndeshje nga një tjetër me të njëjtat kuota.

---

# Tri gjëra të matura që duhen ditur

**1. Outputi ka 14% të variancës së realitetit.**
`sd` e totalit tonë **0.670**, e realitetit **1.773**. Publikojmë total ≥ 4 në
**0.6%** të ndeshjeve; ndodh në **34.3%**.

**2. Outputi parashikohet nga kuotat.**
Me fqinjin më të afërt mbi kuotat e vetme: **47.7%** e skorit tonë dhe **71%**
e drejtimit. I njëjti fqinj e gjen realitetin vetëm në **6.2%**.

**3. Ngushtimi ndodh në hallkën e fundit, jo më parë.**

| | p5 | p50 | p95 | sd |
|---|---|---|---|---|
| P(Over 2.5) e tregut | 0.36 | 0.54 | 0.70 | 0.103 |
| λ jonë | 2.22 | 2.78 | 3.46 | **0.379** |
| totali i publikuar | 1.00 | 2.00 | 3.00 | **0.670** |
| totali real | 0.00 | 3.00 | 6.00 | **1.773** |

λ i dallon ndeshjet. **Zgjedhja e modës e vret atë dallim.**
