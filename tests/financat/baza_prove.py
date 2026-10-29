"""Nje Supabase i rreme, por me te njejtat rregulla si migrimi 7.

Pika: trigeri qe mban 'data' dhe 'kryer_me' te lidhura ekziston ne baze, jo ne
Python. Nese testi nuk e imiton, testi mashtron.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("SUPABASE_SERVICE_KEY", "sk-prove")
os.environ.setdefault("FIN_TOKEN", "token-prove")

from fastapi import HTTPException

ZONA = ZoneInfo("Europe/Tirane")
# Tabelat qe migrimi 7 i njeh; ato jashte listes ngrene PGRST205.
ME_KRYER_ME = {"fin_transaksionet"}
# Kolona 'aktiv' ka default true ne skeme — pa te, filtrat e panelit i heqin
# rreshtat e sapokrijuar dhe testi do te "kalonte" mbi nje panel bosh.
ME_AKTIV = {"fin_llogarite", "fin_planet", "fin_te_ardhurat", "fin_investimet",
            "fin_bizneset", "fin_biznes_zerat", "fin_buxhetet", "fin_personat",
            "fin_rezervat"}


class Baza:
    def __init__(self, tabelat_ekzistuese=None):
        self.te_dhenat = {}
        self.id_e_radhes = {}
        self.ekzistuese = tabelat_ekzistuese   # None = te gjitha ekzistojne
        self.migrimi7 = True

    # ── ndihmesa ─────────────────────────────────────────────────────────
    def rreshtat(self, tabela):
        if self.ekzistuese is not None and tabela not in self.ekzistuese:
            raise HTTPException(404, f"PGRST205: could not find the table "
                                     f"'public.{tabela}' in the schema cache")
        return self.te_dhenat.setdefault(tabela, [])

    def _id(self, tabela):
        self.id_e_radhes[tabela] = self.id_e_radhes.get(tabela, 0) + 1
        return self.id_e_radhes[tabela]

    def _trigeri_i_kohes(self, tabela, i_ri, i_vjeter=None):
        """Imiton fin_vulos_kohen(): data dhe kryer_me nuk ndahen kurre.

        Para migrimit 7 as kolona as trigeri nuk ekzistojne — baza e vjeter
        duhet te sillet si e vjeter, perndryshe testi i saj s'prova asgje.
        """
        if not self.migrimi7:
            i_ri.pop("kryer_me", None)
            return
        if tabela not in ME_KRYER_ME:
            return
        if i_vjeter is None:
            if not i_ri.get("kryer_me"):
                d = i_ri.get("data") or datetime.now(ZONA).date().isoformat()
                i_ri["kryer_me"] = datetime.combine(
                    datetime.fromisoformat(d).date(),
                    datetime.now(ZONA).time(), tzinfo=ZONA).isoformat()
            else:
                i_ri["data"] = self._lokale(i_ri["kryer_me"]).date().isoformat()
            return
        if i_ri.get("kryer_me") != i_vjeter.get("kryer_me"):
            i_ri["data"] = self._lokale(i_ri["kryer_me"]).date().isoformat()
        elif i_ri.get("data") != i_vjeter.get("data"):
            ora_e_vjeter = self._lokale(i_vjeter["kryer_me"]).time()
            i_ri["kryer_me"] = datetime.combine(
                datetime.fromisoformat(i_ri["data"]).date(),
                ora_e_vjeter, tzinfo=ZONA).isoformat()

    @staticmethod
    def _lokale(x):
        return datetime.fromisoformat(str(x)).astimezone(ZONA)

    def _perputhet(self, rresht, params):
        for celes, vlera in (params or {}).items():
            if celes in ("select", "order", "limit", "offset"):
                continue
            teksti = str(vlera)
            if not teksti.startswith("eq."):
                continue
            pritej = teksti[3:]
            aktuale = rresht.get(celes)
            if pritej in ("true", "false"):
                if bool(aktuale) is not (pritej == "true"):
                    return False
            elif str(aktuale) != pritej:
                return False
        return True

    # ── zevendesuesi i _sb ───────────────────────────────────────────────
    def sb(self, tabela, metoda="get", params=None, trupi=None, prefer=None):
        metoda = metoda.lower()
        rreshtat = self.rreshtat(tabela)

        if metoda == "get":
            dalja = [dict(r) for r in rreshtat if self._perputhet(r, params)]
            rendit = (params or {}).get("order")
            if rendit:
                fusha, _, drejtimi = rendit.partition(".")
                dalja.sort(key=lambda r: (r.get(fusha) is None,
                                          str(r.get(fusha) or "")),
                           reverse=(drejtimi == "desc"))
            kufi = (params or {}).get("limit")
            return dalja[:int(kufi)] if kufi else dalja

        if metoda == "post":
            trupat = trupi if isinstance(trupi, list) else [trupi]
            dalja = []
            for t in trupat:
                t = dict(t)
                if not self.migrimi7 and "kryer_me" in t:
                    raise HTTPException(
                        400, "PGRST204: Could not find the 'kryer_me' column "
                             f"of '{tabela}' in the schema cache")
                # merge-duplicates (cilesimet)
                if "merge-duplicates" in (prefer or "") and t.get("celes"):
                    for r in rreshtat:
                        if r.get("celes") == t["celes"]:
                            r.update(t)
                            dalja.append(dict(r))
                            break
                    else:
                        rreshtat.append(dict(t))
                        dalja.append(dict(t))
                    continue
                t.setdefault("id", self._id(tabela))
                if tabela in ME_AKTIV:
                    t.setdefault("aktiv", True)
                t.setdefault("krijuar_me", datetime.now(timezone.utc).isoformat())
                self._trigeri_i_kohes(tabela, t)
                rreshtat.append(t)
                dalja.append(dict(t))
            return dalja

        if metoda == "patch":
            dalja = []
            for r in rreshtat:
                if not self._perputhet(r, params):
                    continue
                if not self.migrimi7 and "kryer_me" in (trupi or {}):
                    raise HTTPException(
                        400, "PGRST204: Could not find the 'kryer_me' column "
                             f"of '{tabela}' in the schema cache")
                i_vjeter = dict(r)
                r.update(trupi or {})
                self._trigeri_i_kohes(tabela, r, i_vjeter)
                if self.migrimi7:
                    r["perditesuar_me"] = datetime.now(timezone.utc).isoformat()
                dalja.append(dict(r))
            return dalja

        if metoda == "delete":
            mbeten, fshire = [], []
            for r in rreshtat:
                (fshire if self._perputhet(r, params) else mbeten).append(r)
            self.te_dhenat[tabela] = mbeten
            return [dict(r) for r in fshire]

        raise AssertionError(f"metode e panjohur: {metoda}")
