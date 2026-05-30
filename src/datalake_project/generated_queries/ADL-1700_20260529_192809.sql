-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5 trend values
-- Source: AMOS (amos_postgres.amos)
-- Created: ADL-1700
-- Folder: Engine

WITH latest_trends AS (
  SELECT
    rt.psn,
    rt.ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value",
    ROW_NUMBER() OVER (PARTITION BY rt.psn ORDER BY rt.ref_date DESC) AS rn
  FROM amos_postgres.amos.rotables_trend rt
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
)
SELECT
  r.partno,
  r.serialno,
  r.psn,
  a.ac_registr,
  DATE_ADD(DATE '1971-12-31', CAST(lt.ref_date AS BIGINT)) AS ref_date,
  lt.trend_type,
  COALESCE(lt.event_perfno_i, '') AS event_perfno_i,
  lt."value",
  a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN latest_trends lt
  ON UPPER(r.psn) = UPPER(lt.psn)
  AND lt.rn = 1
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
WHERE UPPER(a.ac_typ) = UPPER('B737NG')