-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5 trend values
-- Source: amos_postgres.amos (AMOS Acceptance)
-- Owner: Engine Folder
-- Ticket: ADL-1700

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
  DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
  rt.trend_type,
  rt.event_perfno_i,
  rt."value",
  a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
  ON r.psn = rt.psn
INNER JOIN amos_postgres.amos.aircraft a
  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
INNER JOIN apu_latest_dates ald
  ON rt.psn = ald.psn
  AND DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) = ald.latest_ref_date
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
  AND UPPER(rt.trend_type) = UPPER('CT5')