# Publikimi i API-së në tregjet — dosja e plotë

Gjithçka këtu është gati për t'u kopjuar në formularët e platformave.
Numrat janë të matur, jo të shpikur. Mos i ndrysho lart.

---

## 0. Para se të listosh — kontrolli paraprak

Këto duhen **të gjitha** të mbaruara, ndryshe listimi del i vdekur nga dita e parë.

| # | Çfarë | Ku | Si e kontrollon |
|---|---|---|---|
| 1 | `RAPIDAPI_PROXY_SECRET` | Render env | Pa të, **çdo** kërkesë nga RapidAPI kthen 401. Shih shënimin më poshtë. |
| 2 | `ZYLA_PROXY_SECRET` | Render env | E njëjta për Zyla. |
| 3 | `B2B_ADMIN_SECRET` | Render env | Pa të nuk krijon dot çelësa: `/v1/admin/create-key` kthen 401. |
| 4 | `B2B_BASE_URL` | Render env | Vetëm nëse domeni ndryshon nga `soccer1x2-api.onrender.com`. |
| 5 | Tabela `api_keys` | Supabase | Kolonat: `id, celes, aktiv, plan, limit_ditor, perdorime_sot, perdorime_total, data_perdorimit, emri, email`. |
| 6 | `/docs` kthen **404** | Shfletues | Kontrolli kryesor i sigurisë. Nëse hapet, deploy-i s'e kapi kodin e ri. |
| 7 | `/v1/docs` hapet | Shfletues | Dokumentacioni publik. |
| 8 | `/v1/openapi.json` shkarkohet | Shfletues | Ky skedar ngarkohet në çdo platformë. |

**Shënim për sekretet e proxy-t:** ato nuk i zgjedh ti lirisht. RapidAPI dhe Zyla ta japin secila vlerën e vet
kur krijon listimin — ti e kopjon prej tyre dhe e vendos në Render. Ato janë ajo që provon se kërkesa
erdhi vërtet përmes platformës dhe jo nga dikush që e gjeti URL-në tonë dhe po e përdor falas.

**Testi i fundit para se të shtypësh "Publish":**

```bash
# Duhet 401 — pa çelës nuk hyhet
curl -i https://soccer1x2-api.onrender.com/v1/predictions

# Duhet 200 me të dhëna — me çelësin tënd
curl -H "X-API-Key: CELESI_YT" \
     "https://soccer1x2-api.onrender.com/v1/predictions?date=today&limit=3"

# Duhet 404 — dokumentacioni i brendshëm i mbyllur
curl -i -o /dev/null -w "%{http_code}\n" https://soccer1x2-api.onrender.com/docs
```

---

## 1. Emri dhe përshkrimet

### Emri
```
SOCCER1X2 PRO — Football Predictions API
```

### Përshkrimi i shkurtër (një rresht, deri 100 shkronja)
```
Calibrated football predictions: exact scores, 1X2, O/U and BTTS from 50k Monte Carlo simulations.
```

### Përshkrimi i mesëm (deri 300 shkronja)
```
Football match predictions from a hybrid engine: gradient-boosted expected goals blended with
market-implied strength, then 50,000 Monte Carlo simulations per fixture with a Dixon-Coles
low-score correction. Every probability is calibrated against settled results, and the archive
is published.
```

### Përshkrimi i gjatë (faqja e listimit)

```markdown
## Predictions you can actually price

Most prediction APIs hand you a pick. This one hands you a probability — and tells you how
well those probabilities have held up.

### The engine

Each fixture goes through four stages:

1. **Expected goals** from a gradient-boosted model, blended from four sources: recent form,
   a dynamic ELO rating, market-implied strength, and league baselines.
2. **Normalisation** against settled results, so simulated goal totals match reality rather
   than drifting.
3. **50,000 Monte Carlo simulations**, producing a full scoreline distribution.
4. **Dixon-Coles correction**, which fixes the well-known under-dispersion of independent
   Poisson models at low scores (0-0, 1-0, 0-1, 1-1).

### Calibration, measured and published

Over a 1,017-match archive the engine promised an 11.25% exact-score hit rate and delivered
10.72% — a calibration ratio of 0.953. That is the number that matters: when this API says
something has a 12% chance, it happens about 12% of the time.

Across the full archive:

| Metric | Result |
|---|---|
| Exact scoreline, top pick | 10.9% |
| Exact scoreline, within top 3 | 29.6% |
| Match outcome (1X2) direction | 52.5% |

These are pooled numbers across every league covered, including low-information fixtures.
They are not cherry-picked windows.

### What you get per fixture

- **Exact score** with fair odds, plus the three most likely scorelines with probabilities
- **1X2** and double chance (1X, X2, 12)
- **Over/Under** 1.5, 2.5, 3.5
- **Both teams to score** (GG/NG)
- **Half-time** variants of the above
- **Confidence** score and a single highest-edge pick per fixture

All `fair_odds` fields are `1 / probability` — no bookmaker margin applied. Compare them
against real prices to find your own edge.

### Coverage

Today's and tomorrow's fixtures. Call `/v1/leagues` for the live list of covered competitions
and fixture counts.

### Honest limits

- Coverage is **today and tomorrow only**. Historical queries are not available on this API.
- Free keys are capped at **100 requests/day**, resetting at midnight Europe/Tirane.
- These are statistical estimates. **No outcome is guaranteed, and this is not betting advice.**
- Football is high-variance. A 12% probability is right about 12% of the time — which means
  it is wrong about 88% of the time. Use these as inputs to a model, not as tips.
```

### Kategoritë
Zgjidh sipas platformës: `Sports` → `Data` → `Artificial Intelligence / Machine Learning`.

### Etiketat (tags)
```
football, soccer, predictions, betting, odds, correct score, monte carlo,
expected goals, xg, statistics, sports data, machine learning
```

---

## 2. Planet e çmimeve — propozim

Kjo është e jotja për ta vendosur. Ky është një pikënisje e zakonshme për këtë kategori.
Kufijtë vendosen te `limit_ditor` në tabelën `api_keys` (ose te vetë platforma, për trafikun proxy).

| Plani | Kërkesa | Çmimi/muaj | Kujt i shërben |
|---|---|---|---|
| **Basic** | 100/ditë | Falas | Provë, zhvillim, vlerësim |
| **Pro** | 1,000/ditë | $19 | Një sajt ose bot i vogël |
| **Ultra** | 10,000/ditë | $79 | Prodhim, disa klientë |
| **Mega** | Pa kufi | $249 | Rishpërndarje |

**Këshillë:** mos e bëj planin falas shumë bujar. Në këtë kategori, mbulimi sot+nesër do të thotë
që 100 kërkesa/ditë janë tashmë të mjaftueshme për një përdorues të vetëm — pra çdo gjë mbi këtë
e humb klientin që paguan.

---

## 3. Platformat, sipas radhës

### 3.1 RapidAPI — **e para**

Më e madhja, dhe kodi ynë tashmë e mbështet (`X-RapidAPI-Proxy-Secret`).

1. Hyr në `rapidapi.com/provider` → **Add New API**
2. **Import from OpenAPI** → ngarko `https://soccer1x2-api.onrender.com/v1/openapi.json`
3. Te **Settings → Base URL**: `https://soccer1x2-api.onrender.com`
4. Te **Security → Proxy Secret**: kopjo vlerën që të jep RapidAPI → vendose në Render si
   `RAPIDAPI_PROXY_SECRET` → **ribëj deploy**
5. Vendos planet (seksioni 2)
6. Ngarko përshkrimet (seksioni 1) dhe logon
7. Testo çdo endpoint nga vetë RapidAPI përpara publikimit

⚠️ Hapi 4 është aty ku dështojnë shumica. Pa atë sekret në Render, listimi duket i përsosur
dhe çdo kërkesë kthen 401.

### 3.2 Zyla API Hub

Gjithashtu i mbështetur në kod (`X-Zyla-Secret`).

1. Apliko si ofrues te `zylalabs.com`
2. Ngarko të njëjtin `openapi.json`
3. Sekreti vendoset te **Access Control** → kopjoje në Render si `ZYLA_PROXY_SECRET`
4. Zyla e shqyrton me dorë — prit disa ditë

### 3.3 APILayer

Nuk ka mbështetje proxy të veçantë në kodin tonë, ndaj përdor çelësa `X-API-Key` direkt:
krijo një çelës me `/v1/admin/create-key` dhe jepja atyre.

### 3.4 Postman Public API Network

Falas dhe i shpejtë. Importo `openapi.json` në një koleksion, publikoje si workspace publik.
Nuk sjell pagesa direkt, por sjell zhvillues dhe lidhje.

### 3.5 Të tjera pa shumë punë

`apis.guru`, `publicapis.dev`, `apilist.fun`, `any-api.com` — listime falas, dërgo URL-në e skemës.

---

## 4. Dy gjëra që duhen vendosur para listimit

### 4.1 Kuotat e vërteta në përgjigje — pyetje për kushtet e API-Sports

Fusha `markets[...].odds` kthen kuotat **reale të bukmejkerit** kur i kemi (nga `odds_reale`),
dhe bie te kuota e drejtë vetëm kur nuk i kemi.

Ato kuota vijnë nga API-Sports. Parashikimet tona janë punë e jona dhe rishitja e tyre s'ka
problem — por **rishpërndarja e kuotave të papërpunuara të tyre përmes një API-je me pagesë
është gjë tjetër**, dhe zakonisht kufizohet nga kushtet e planit.

Nuk jam jurist dhe nuk i kam lexuar kushtet e planit tënd. Por është pikërisht lloji i gjërave
që një treg API-sh e verifikon, ose që vjen si ankesë tre muaj pas listimit.

**Zgjidhja, nëse do ta heqësh fare pyetjen:** kthe gjithmonë kuotën e drejtë (`1/probabilitet`)
dhe mos e kthe kurrë kuotën e bukmejkerit. Është një ndryshim i vogël në `_b2b_match`.
Humbet pak vlerë për klientin, fiton siguri të plotë. Thuaj një fjalë dhe e bëj.

### 4.2 Repoja publike

E vendose: **bëje private**. Bëje para se të listosh, sepse listimi çon zhvillues te emri ynë
dhe prej andej te GitHub.

`github.com/Drini30/soccer1x2-api` → **Settings** → poshtë fare, **Danger Zone** →
**Change repository visibility** → **Make private**.

Render vazhdon të bëjë deploy njësoj — lidhja mbetet e autorizuar. Asgjë nuk prishet.

Historiku i git-it përmban çelësin `anon` të Supabase-it në katër commit-e të vjetra. Ai çelës
është projektuar të jetë publik (është ai që shkon në shfletues) dhe është i padëmshëm **nëse
RLS është i ndezur** në tabelat e tua. Çelësi `service_role` nuk është bërë kurrë commit — e
kontrollova gjithë historikun. Pra këtu nuk ka urgjencë; vetëm sigurohu që RLS është aktiv.

---

## 5. Politika e pretendimeve — mos e shkel

Kjo kategori mbikëqyret. Një pretendim i tepruar e heq listimin.

**Lejohet, sepse është e matur:**
- "Calibration ratio 0.953 over a 1,017-match archive"
- "29.6% of matches finish on one of our top three scorelines"
- "52.5% direction accuracy"

**Nuk lejohet, sepse nuk është e vërtetë:**
- "Guaranteed profit" / "Sure wins" / "95% accuracy"
- Çdo normë fitimi ose ROI që nuk e kemi matur mbi arkivin
- Të fshehësh që mbulimi është vetëm sot+nesër

Mbaje rreshtin **"This is not betting advice"** në çdo listim. Është edhe e vërtetë, edhe
mbrojtja jote.
