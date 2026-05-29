-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5 trend data
-- Source: AMOS (amos_postgres.amos)
-- Owner: ASL Airlines
-- Ticket: ADL-1700

WITH apu_latest AS (
  SELECT
    r.partno,
    r.serialno,
    r.psn,
    rt.ac_registr,
    DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value",
    ROW_NUMBER() OVER (PARTITION BY r.psn ORDER BY rt.ref_date DESC) AS rn
  FROM amos_postgres.amos.rotables r
  INNER JOIN amos_postgres.amos.rotables_trend rt
    ON UPPER(r.psn) = UPPER(rt.psn)
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
)
SELECT
  apu.partno,
  apu.serialno,
  apu.psn,
  apu.ac_registr,
  apu.ref_date,
  apu.trend_type,
  apu.event_perfno_i,
  apu."value",
  a.ac_typ
FROM apu_latest apu
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(apu.ac_registr) = UPPER(a.ac_registr)
WHERE apu.rn = 1
  AND UPPER(a.ac_typ) = UPPER('B737NG')
ORDER BY apu.psn, apu.ref_date DESC