-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest reference dates
-- Source: AMOS Acceptance
-- Owner: Engine Folder
-- Last Updated: 2024

WITH latest_apu_trends AS (
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
  r.ac_registr,
  DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
  rt.trend_type,
  rt.event_perfno_i,
  rt."value",
  a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON r.psn = rt.psn
INNER JOIN latest_apu_trends lat
  ON rt.psn = lat.psn
  AND rt.ref_date = lat.max_ref_date
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
  AND UPPER(rt.trend_type) = UPPER('CT5')