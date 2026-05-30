-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5ATP trend values
-- Source: AMOS (amos_postgres.amos)
-- Owner: Engine Folder
-- Last Updated: ADL-1700

WITH latest_trends AS (
  SELECT
    rt.psn,
    rt.ref_date,
    ROW_NUMBER() OVER (PARTITION BY rt.psn ORDER BY rt.ref_date DESC) AS rn
  FROM amos_postgres.amos.rotables_trend rt
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
)
SELECT
  r.partno,
  r.serialno,
  r.psn,
  r.ac_registr,
  rt.ref_date,
  rt.trend_type,
  rt.event_perfno_i,
  rt."value",
  a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON r.psn = rt.psn
INNER JOIN latest_trends lt
  ON rt.psn = lt.psn
  AND rt.ref_date = lt.ref_date
  AND lt.rn = 1
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
  AND UPPER(rt.trend_type) = UPPER('CT5')