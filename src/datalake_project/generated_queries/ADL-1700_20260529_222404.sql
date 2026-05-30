-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft from AMOS rotables and trends
-- Source: amos_postgres.amos (AMOS Acceptance)
-- Created: ADL-1700
-- Last Updated: 2024

WITH apu_latest_dates AS (
  SELECT
    r.psn,
    MAX(rt.ref_date) AS max_ref_date
  FROM amos_postgres.amos.rotables r
  INNER JOIN amos_postgres.amos.rotables_trend rt
    ON r.psn = rt.psn
  INNER JOIN amos_postgres.amos.aircraft a
    ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
  WHERE UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
  GROUP BY r.psn
)
SELECT DISTINCT
  r.partno,
  r.serialno,
  r.psn,
  r.ac_registr,
  DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
  rt.trend_type,
  COALESCE(rt.event_perfno_i, '') AS event_perfno_i,
  rt."value" AS "value",
  a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON r.psn = rt.psn
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
INNER JOIN apu_latest_dates ald
  ON r.psn = ald.psn
  AND rt.ref_date = ald.max_ref_date
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
  AND UPPER(rt.trend_type) = UPPER('CT5')