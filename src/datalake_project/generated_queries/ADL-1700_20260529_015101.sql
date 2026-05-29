-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft with latest CT5 trend values
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Owner: Engine Folder
-- Last Updated: ADL-1700

WITH apu_latest_ref_date AS (
  SELECT
    rt.psn,
    MAX(rt.ref_date) AS max_ref_date
  FROM amos_postgres.amos.rotables_trend rt
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
  GROUP BY rt.psn
)
SELECT
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
  ON UPPER(r.psn) = UPPER(rt.psn)
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
INNER JOIN apu_latest_ref_date ald
  ON rt.psn = ald.psn
  AND rt.ref_date = ald.max_ref_date
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
  AND UPPER(rt.trend_type) = UPPER('CT5')