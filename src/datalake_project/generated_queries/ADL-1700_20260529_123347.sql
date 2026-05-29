-- VDS: APU Health Monitor
-- Folder: Engine
-- Source: amos_postgres.amos (AMOS Acceptance)
-- Purpose: Extract APU performance data for B737NG aircraft with latest CT5 trend values
-- Last Updated: ADL-1700

WITH apu_latest_date AS (
  SELECT
    UPPER(rt.psn) AS psn,
    MAX(DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT))) AS max_ref_date
  FROM amos_postgres.amos.rotables_trend rt
  WHERE UPPER(rt.trend_type) = UPPER('CT5')
  GROUP BY UPPER(rt.psn)
)
SELECT DISTINCT
  UPPER(r.partno) AS partno,
  UPPER(r.serialno) AS serialno,
  UPPER(r.psn) AS psn,
  UPPER(ac.ac_registr) AS ac_registr,
  UPPER(rt.psn) AS rt_psn,
  DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
  UPPER(rt.trend_type) AS trend_type,
  COALESCE(rt.event_perfno_i, '') AS event_perfno_i,
  rt."value" AS "value",
  UPPER(ac.ac_typ) AS ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON UPPER(r.psn) = UPPER(rt.psn)
INNER JOIN amos_postgres.amos.aircraft ac
  ON UPPER(ac.ac_typ) = UPPER('B737NG')
INNER JOIN apu_latest_date ald
  ON UPPER(rt.psn) = UPPER(ald.psn)
  AND DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) = ald.max_ref_date
WHERE UPPER(rt.trend_type) = UPPER('CT5')
  AND UPPER(ac.ac_typ) = UPPER('B737NG')