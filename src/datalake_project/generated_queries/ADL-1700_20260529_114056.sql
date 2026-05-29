-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft with latest CT5 trend data
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Owner: Engine Folder
-- Ticket: ADL-1700

WITH ranked_trends AS (
  SELECT
    r.partno,
    r.serialno,
    r.psn,
    rt.psn AS rt_psn,
    rt.ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value",
    a.ac_registr,
    a.ac_typ,
    ROW_NUMBER() OVER (PARTITION BY r.psn ORDER BY rt.ref_date DESC) AS rn
  FROM amos_postgres.amos.rotables r
  INNER JOIN amos_postgres.amos.rotables_trend rt
    ON UPPER(r.psn) = UPPER(rt.psn)
  INNER JOIN amos_postgres.amos.aircraft a
    ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
  WHERE UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
)
SELECT
  partno,
  serialno,
  psn,
  rt_psn,
  DATE_ADD(DATE '1971-12-31', CAST(ref_date AS BIGINT)) AS ref_date,
  trend_type,
  event_perfno_i,
  value,
  ac_registr,
  ac_typ
FROM ranked_trends
WHERE rn = 1