# Propozim: ruajtja e λ-së që simulohet — I PAAPLIKUAR

Asgjë këtu nuk është te kodi që punon. `soccer_api.py` është i paprekur.
Aplikohet vetëm pas OK-së së pronarit.

| skedari | çfarë është |
|---|---|
| `lambda.patch` | Ndryshimi i propozuar te `soccer_api.py`. Shton te `training_data` λ-në që hyn në simulim (`lam_1`, `lam_2`), hapat e zinxhirit (`lam_n_*`, `xg_norm`, `lam_treg`, `shk_treg`, `aff`) dhe gjurmën e zgjedhjes (`zgjedhja`: top-5, drejtimi, LEAN, fallback, shenja e gjenerimit). Asnjë output i publikuar nuk ndryshon. |
| `filtri_build.patch` | Pa këtë, vula e re `build` i nxjerr në heshtje ndeshjet e reja nga `sql/filtri/2` dhe `/3`. |
| `kontrolli_lambda.sql` | Pas deploy-it: a i kanë rreshtat e rinj çelësat, dhe sa gjurmë i përkasin skorit të publikuar. |
| `test_patch.py` | Prova që outputi s'ndryshon (10,080 raste simulimi, 290 analiza të plota, dy gjenerime me ngrirjen e vërtetë). Kërkon `soccer_api.patched.py` pranë tij: `cp ../../soccer_api.py soccer_api.patched.py && patch soccer_api.patched.py lambda.patch`. |
| `test_output.txt` | Outputi i provës së fundit: TË GJITHA KONTROLLET KALUAN. |
| `harness.py` | Kopje e saktë e hallkave 9–12 (simulimi + zgjedhja). Me λ të ruajtura riprodhon skorin ndeshje për ndeshje. |

Kufiri i tij: `training_data` mbishkruhet në çdo rigjenerim, kurse skori ngrihet
nga gjenerimi i parë. Pra λ e ruajtur këtu është ajo e **fundit para fillimit**:
e saktë për "λ kundrejt rezultatit real", jo gjithmonë ajo pas skorit të
publikuar. Shih `docs/zinxhiri-i-llogaritjes.md`, seksioni *Gjenerimet*.
