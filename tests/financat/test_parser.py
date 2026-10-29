import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from datetime import date
import asistenti as A

SOT = date(2026, 9, 28)
G = {
  "llogarite": [{"id":1,"emri":"Ndricim Plaku","lloji":"bank","monedha":"ALL"},
                {"id":2,"emri":"Kesh","lloji":"cash","monedha":"ALL"},
                {"id":3,"emri":"Raiffeisen kursim","lloji":"kursim","monedha":"EUR"}],
  "personat": [{"id":1,"emri":"Drini"},{"id":2,"emri":"Elsa"}],
  "planet": [{"id":10,"emri":"Interneti","shuma":2500,"monedha":"ALL","aktiv":True,
              "kategoria":"sherbime","llogaria_id":2},
             {"id":11,"emri":"Qiraja","shuma":35000,"monedha":"ALL","aktiv":True,
              "kategoria":"banese","llogaria_id":1},
             {"id":12,"emri":"Drita dhe uji","shuma":4200,"monedha":"ALL","aktiv":True}],
  "te_ardhurat": [{"id":20,"emri":"Rroga","lloji":"page","shuma_mujore":95000,
                   "monedha":"ALL","aktiv":True,"llogaria_id":1,"personi_id":1},
                  {"id":21,"emri":"Soccer1x2","lloji":"biznes","shuma_mujore":None,
                   "monedha":"EUR","aktiv":True}],
  "detyrimet": [{"id":30,"pala":"Banka Kombetare","shuma_totale":400000,
                 "shuma_paguar":120000,"monedha":"ALL","kesti_mujor":18000,
                 "statusi":"aktiv"},
                {"id":31,"pala":"Shoku Ilir","shuma_totale":20000,
                 "shuma_paguar":0,"monedha":"ALL","statusi":"aktiv"}],
}
C = {"monedha_baze": "ALL"}

RASTET = [
 # (fjalia, veprimi i pritur, kontrolle)
 ("shto si te paguar internetin", "pagese_plani", {"burimi.id":10,"shuma":2500}),
 ("shenoje qiran si te paguar", "pagese_plani", {"burimi.id":11,"shuma":35000}),
 ("e paguajta driten 4500 lek", "pagese_plani", {"burimi.id":12,"shuma":4500}),
 ("shto rrogen te Ndricim Plaku 95000 lek", "hyrje",
  {"burimi.id":20,"shuma":95000.0,"llogaria.id":1,"monedha":"LEK"}),
 ("mora rrogen", "hyrje", {"burimi.id":20,"shuma":95000.0}),
 ("mora 120 mije nga rroga", "hyrje", {"shuma":120000.0}),
 ("me erdhi rroga 95 mije leke dje", "hyrje",
  {"shuma":95000.0,"data":"2026-09-27"}),
 ("shpenzova 1200 leke per ushqime", "shpenzim",
  {"shuma":1200.0,"kategoria":"ushqime","llogaria.id":2}),
 ("1200 lek karburant", "shpenzim", {"shuma":1200.0,"kategoria":"karburant"}),
 ("bleva veshje 8.500 leke", "shpenzim", {"shuma":8500.0,"kategoria":"veshje"}),
 ("bleva kafe 300 lek ne oren 9:30", "shpenzim", {"shuma":300.0,"ora":"09:30"}),
 ("paguaj borxhin e bankes 10000", "borxh", {"burimi.id":30,"shuma":10000.0}),
 ("i ktheva shokut ilir 5 mije", "borxh", {"burimi.id":31,"shuma":5000.0}),
 ("shlyeva kestin e bankes", "borxh", {"burimi.id":30,"shuma":18000.0}),
 ("rezervo 50 mije per taksat", "rezervim", {"shuma":50000.0}),
 ("vendos menjane 20000 leke per emergjence", "rezervim", {"shuma":20000.0}),
 ("kalo 10000 nga kesh te Ndricim Plaku", "transfer",
  {"shuma":10000.0,"llogaria.id":2,"destinacioni.id":1}),
 ("vendos buxhet 30000 per ushqime", "buxhet",
  {"shuma":30000.0,"kategoria":"ushqime"}),
 ("sa kam?", "pyetje_gjendje", {}),
 ("sa me ka mbetur", "pyetje_gjendje", {}),
 ("cfare kam per te paguar", "pyetje_detyrime", {}),
 ("sa shpenzova kete muaj", "pyetje_shpenzime", {}),
 ("bla bla bla", "pa_kuptuar", {}),
 # raste me te veshtira
 ("shto si te paguar internetin nga kesh", "pagese_plani",
  {"burimi.id":10,"llogaria.id":2}),
 ("pagova 2500 per internetin me 25/09", "pagese_plani",
  {"burimi.id":10,"shuma":2500.0,"data":"2026-09-25"}),
 ("paguajta qiran 35 mije nga Ndricim Plaku me 1 shtator", "pagese_plani",
  {"burimi.id":11,"shuma":35000.0,"llogaria.id":1,"data":"2026-09-01"}),
 ("shpenzova 450 lek per kafe sot ne oren 14:20", "shpenzim",
  {"shuma":450.0,"kategoria":"kafe","ora":"14:20","data":"2026-09-28"}),
 # mungesa duhet te pyese, jo te hamendesoje
 ("shpenzova per ushqime", "shpenzim", {"shuma":None}),
 ("shto si te paguar", "pagese_plani", {"burimi":None}),
 ("rezervo per taksat", "rezervim", {"shuma":None}),
]

def merr(p, rruga):
    v = p
    for c in rruga.split("."):
        v = (v or {}).get(c) if isinstance(v, dict) else None
    return v

ok = keq = 0
for fjalia, pritej, kontrollet in RASTET:
    p = A.kupto(fjalia, G, C, SOT)
    probleme = []
    if p["veprimi"] != pritej:
        probleme.append(f"veprimi={p['veprimi']} (pritej {pritej})")
    for rruga, vlera in kontrollet.items():
        aktuale = merr(p, rruga)
        if aktuale != vlera:
            probleme.append(f"{rruga}={aktuale!r} (pritej {vlera!r})")
    if probleme:
        keq += 1
        print(f"  ✗ {fjalia!r}\n      " + "\n      ".join(probleme))
        print(f"      mungon={p['mungon']} siguria={p['siguria']}")
    else:
        ok += 1
        print(f"  ✓ {fjalia!r}  →  {A.permbledh(p, C)}")

print(f"\n{'='*62}\nOK: {ok}   DESHTIME: {keq}\n{'='*62}")
sys.exit(1 if keq else 0)
