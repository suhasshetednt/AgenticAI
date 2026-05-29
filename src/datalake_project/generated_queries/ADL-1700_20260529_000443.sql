-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft with latest reference dates
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Owner: ASL Airlines
-- Folder: Engine

WITH latest_apu_trends AS (
  SELECT
    rt.psn,
    rt.ref_date,
    ROW_NUMBER() OVER (PARTITION BY rt.psn ORDER BY rt.ref_date DESC) AS rn
  FROM amos_postgres.amos.rotables_trend rt
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
)
SELECT DISTINCT
  r.partno,
  r.serialno,
  r.psn,
  a.ac_registr,
  rt.psn AS rt_psn,
  DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
  rt.trend_type,
  COALESCE(rt.event_perfno_i, '') AS event_perfno_i,
  rt."value",
  a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON UPPER(r.psn) = UPPER(rt.psn)
INNER JOIN latest_apu_trends lat
  ON rt.psn = lat.psn
  AND rt.ref_date = lat.ref_date
  AND lat.rn = 1
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(a.ac_typ) = UPPER('B737NG')
WHERE UPPER(rt.trend_type) = UPPER('CT5')
ORDER BY a.ac_registr, r.psn, rt.ref_date DESC