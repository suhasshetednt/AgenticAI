-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft with latest CT5 trend data
-- Source: amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
-- Owner: Engine Folder
-- Ticket: ADL-1700

WITH latest_apu_trends AS (
  SELECT
    rt.partno,
    rt.serialno,
    rt.psn,
    rt.ac_registr,
    DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value",
    ROW_NUMBER() OVER (PARTITION BY rt.psn ORDER BY rt.ref_date DESC) AS rn
  FROM amos_postgres.amos.rotables_trend rt
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
)
SELECT
  lat.partno,
  lat.serialno,
  lat.psn,
  lat.ac_registr,
  lat.ref_date,
  lat.trend_type,
  lat.event_perfno_i,
  lat."value",
  a.ac_typ
FROM latest_apu_trends lat
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(lat.ac_registr) = UPPER(a.ac_registr)
WHERE rn = 1
  AND UPPER(a.ac_typ) = UPPER('B737NG')
ORDER BY lat.psn, lat.ref_date DESC