-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Last Updated: ADL-1700
-- Owner: Engine Folder

WITH apu_latest_dates AS (
  SELECT
    rt.psn,
    MAX(DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT))) AS latest_ref_date
  FROM amos_postgres.amos.rotables_trend rt
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
  GROUP BY rt.psn
)
SELECT
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
  AND UPPER(rt.trend_type) = UPPER('CT5')
INNER JOIN apu_latest_dates ald
  ON UPPER(rt.psn) = UPPER(ald.psn)
  AND DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) = ald.latest_ref_date
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(a.ac_typ) = UPPER('B737NG')
WHERE UPPER(a.ac_typ) = UPPER('B737NG')