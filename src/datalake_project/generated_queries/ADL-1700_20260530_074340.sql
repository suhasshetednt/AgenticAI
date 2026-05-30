-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft with latest CT5ATP trend values
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Owner: Engine Folder
-- Last Updated: ADL-1700

WITH ranked_trends AS (
  SELECT
    r.partno,
    r.serialno,
    r.psn,
    rt.ac_registr,
    rt.ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value",
    a.ac_typ,
    ROW_NUMBER() OVER (PARTITION BY r.psn ORDER BY rt.ref_date DESC) AS rn
  FROM amos_postgres.amos.rotables r
  INNER JOIN amos_postgres.amos.rotables_trend rt
    ON r.psn = rt.psn
  INNER JOIN amos_postgres.amos.aircraft a
    ON UPPER(rt.ac_registr) = UPPER(a.ac_registr)
  WHERE UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
)
SELECT
  partno,
  serialno,
  psn,
  ac_registr,
  DATE_ADD(DATE '1971-12-31', CAST(ref_date AS BIGINT)) AS ref_date,
  trend_type,
  event_perfno_i,
  value,
  ac_typ
FROM ranked_trends
WHERE rn = 1