-- ==========================================================
-- FSHIRJE E PARASHIKIMEVE TË PALUAJTURA + RIGJENERIM
-- ==========================================================
-- Qëllimi: parashikimet e gjeneruara ndërsa Render kishte env-var të ngelura u
-- prodhuan me kalibrimin e VJETËR (λ ≈ 2.255 në vend të 2.613). Ato duhen hedhur
-- dhe rikrijuar tani që vlerat e sakta janë aktive.
--
-- ⚠️ KORRIGJIM (gusht 2026): versioni i parë përdorte `rezultati IS NULL` si kusht
--    mbrojtës. Ai kusht NUK PËRPUTHET KURRË — kolona `rezultati` mban "0 - 0" për
--    ndeshjet e paluajtura, jo NULL. Pra skripti i vjetër nuk fshinte asgjë.
--    Diskriminuesi i saktë është `statusi`: NS/TBD për të paluajtura, FT/AET për
--    të kryera. Kjo duket edhe te `ora` — orë reale kundrejt tekstit "FT".
--
-- ⚠️ RREGULLI QË S'DUHET THYER: NUK preken parashikimet e ndeshjeve TË LUAJTURA.
--    Ato janë arkivi mbi të cilin qëndron çdo matje që kemi bërë — rikalibrimi
--    i λ-së, Platt-i, matja e is_value, /api/performanca. Fshirja e tyre do të
--    shkatërronte bazën e provave dhe s'do të rikthehej dot.
--    Prandaj çdo DELETE më poshtë filtron mbi `statusi`, dhe hapi 5 e krahason
--    numrin e arkivit para dhe pas.
--
-- ⚠️ PROVABLY FAIR: hash-i është premtim publik. Nëse një commitment i është
--    shfaqur tashmë një përdoruesi dhe ti e fshin e rigjeneron, premtimi i
--    publikuar nuk përputhet më me parashikimin e ri. Për ndeshje ende të
--    paluajtura ku askush s'ka vepruar, rreziku është i vogël — por dije se
--    kjo është zgjedhje produkti, jo thjesht teknike.
--
-- EKZEKUTOJI ME RADHË. Hapat 1-2 nuk fshijnë asgjë.
-- ==========================================================


-- ══════════════════════════════════════════════════════════
-- HAPI 1 — SHIKO ÇFARË DO TË FSHIHET (asgjë s'preket)
-- ══════════════════════════════════════════════════════════
-- `mbeten_arkiv` është arkivi që MBETET. Nëse ai numër është afër 329 ose më
-- shumë, gjithçka është në rregull. Nëse del 0, NDALU — diçka s'shkon me kushtin.
SELECT count(*) FILTER (WHERE statusi IS NULL
                        OR statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
         AS do_fshihen,
       count(*) FILTER (WHERE statusi IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
         AS mbeten_arkiv,
       count(*) AS gjithsej
FROM predictions;


-- ══════════════════════════════════════════════════════════
-- HAPI 2 — Ndarja sipas datës, që të shohësh a ka gjë të vjetër
-- ══════════════════════════════════════════════════════════
-- Pritet vetëm sot/nesër/pasnesër. Nëse dalin data të vjetra ende me statusi NS,
-- ato janë ndeshje që s'u përditësuan kurrë — fshihen njësoj, s'kanë vlerë.
SELECT data, count(*) AS sa
FROM predictions
WHERE statusi IS NULL
   OR statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD')
GROUP BY data ORDER BY data;


-- ══════════════════════════════════════════════════════════
-- HAPI 3 — Fshi commitment-et e pahapura
-- ══════════════════════════════════════════════════════════
-- Vetëm 'kycur' (të kyçura, ende të pazbuluara). Rreshtat 'zbuluar' janë prova
-- publike e ndeshjeve të kryera — ato MBETEN.
DELETE FROM provably_fair WHERE statusi = 'kycur';


-- ══════════════════════════════════════════════════════════
-- HAPI 4 — Fshi parashikimet e paluajtura
-- ══════════════════════════════════════════════════════════
-- Filtrimi bëhet VETËM mbi `statusi`. Çdo rresht me status përfundimtar (FT/AET/
-- PEN/AWD/WO/CANC/PST/ABD) mbetet i paprekur — ai është arkivi.
DELETE FROM predictions
WHERE statusi IS NULL
   OR statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD');


-- ══════════════════════════════════════════════════════════
-- HAPI 5 — VERIFIKO
-- ══════════════════════════════════════════════════════════
-- `mbeten_arkiv` duhet të jetë I NJËJTË me numrin e hapit 1. Nëse ka rënë,
-- kushti ka prekur arkivin — thuaje menjëherë.
SELECT count(*) FILTER (WHERE statusi IS NULL
                        OR statusi NOT IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
         AS mbeten_te_paluajtura,
       count(*) FILTER (WHERE statusi IN ('FT','AET','PEN','AWD','WO','CANC','PST','ABD'))
         AS mbeten_arkiv
FROM predictions;

SELECT statusi, count(*) FROM provably_fair GROUP BY statusi;


-- ══════════════════════════════════════════════════════════
-- HAPI 6 — RIGJENERO (jo SQL — thirre në shfletues)
-- ══════════════════════════════════════════════════════════
-- Parametri ?date= detyron pjesën e rëndë menjëherë, pa throttle. Pa të, cron-i
-- do ta bënte vetë por deri në HEAVY_GEN_INTERVAL më vonë.
--
--   https://soccer1x2-api.onrender.com/api/cron/gjenero?date=2026-08-02
--
-- Ndryshoje datën për secilën ditë që do (sot, nesër, pasnesër).
-- Zgjat një-dy minuta për ditë — Monte Carlo plus paginim kuotash.
--
-- Pastaj kontrollo që parashikimet e reja mbajnë kalibrimin e ri:
--
-- SELECT ndeshja, rezultati_sakt, besueshmeria
-- FROM predictions WHERE statusi = 'NS'
-- ORDER BY id DESC LIMIT 20;
--
-- Skorët "1-0", "2-1", "1-1" duhet të shfaqen tani rregullisht. Nëse sheh ende
-- vetëm "0-0" dhe skorë shumë të ulët, kalibrimi s'ka hyrë në fuqi — rikontrollo
-- /api/status.
