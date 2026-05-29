-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft with latest CT5 trend data
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Owner: ASL Airlines
-- Ticket: ADL-1700

WITH latest_trends AS (
  SELECT
    rt.psn,
    MAX(DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT))) AS max_ref_date
  FROM amos_postgres.amos.rotables_trend rt
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
  GROUP BY rt.psn
)
SELECT DISTINCT
  r.partno,
  r.serialno,
  r.psn,
  a.ac_registr,
  DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
  rt.trend_type,
  COALESCE(rt.event_perfno_i, '') AS event_perfno_i,
  rt."value",
  a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON r.psn = rt.psn
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
INNER JOIN latest_trends lt
  ON rt.psn = lt.psn
  AND DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) = lt.max_ref_date
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
  AND UPPER(rt.trend_type) = UPPER('CT5')
ORDER BY a.ac_registr, r.psn, rt.ref_date DESC