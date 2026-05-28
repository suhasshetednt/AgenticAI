-- VDS: APU Health Monitor
-- Description: Health monitoring query for APUs fitted to ASL B737NG aircraft
-- Source: AMOS (amos_postgres.amos)
-- Tables: rotables, rotables_trend, aircraft
-- Purpose: Provides current CT5ATP trend values, workorder references, and aircraft registration for each APU
-- Created: ADL-1700

WITH latest_trends AS (
  SELECT
    psn,
    MAX(DATE_ADD(DATE '1971-12-31', CAST(ref_date AS BIGINT))) AS latest_ref_date
  FROM amos_postgres.amos.rotables_trend
  WHERE UPPER(trend_type) = UPPER('CT5')
  GROUP BY psn
)
SELECT
  r.partno,
  r.serialno,
  r.psn,
  UPPER(a.ac_registr) AS ac_registr,
  UPPER(a.ac_typ) AS ac_typ,
  DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
  rt.trend_type,
  rt.event_perfno_i,
  rt."value"
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON r.psn = rt.psn
INNER JOIN latest_trends lt
  ON rt.psn = lt.psn
  AND DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) = lt.latest_ref_date
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
  AND UPPER(rt.trend_type) = UPPER('CT5')
ORDER BY a.ac_registr, r.serialno, rt.ref_date DESC