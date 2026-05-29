-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5 trend values
-- Source: AMOS (amos_postgres.amos)
-- Owner: Engine Folder
-- Last Updated: ADL-1700

WITH apu_latest_dates AS (
  SELECT
    rt.psn,
    MAX(DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT))) AS latest_ref_date
  FROM amos_postgres.amos.rotables_trend rt
  WHERE rt.trend_type = 'CT5'
  GROUP BY rt.psn
)
SELECT
  r.partno,
  r.serialno,
  r.psn,
  a.ac_registr,
  DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
  rt.trend_type,
  rt.event_perfno_i,
  rt."value",
  a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON r.psn = rt.psn
INNER JOIN apu_latest_dates ald
  ON rt.psn = ald.psn
  AND DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) = ald.latest_ref_date
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
  AND rt.trend_type = 'CT5'
ORDER BY a.ac_registr, r.psn, rt.ref_date DESC