-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5 trend data
-- Source: amos_postgres.amos (AMOS Acceptance)
-- Created: ADL-1700
-- Owner: Engine Folder
-- Last Updated: 2024

SELECT DISTINCT
    r.partno,
    r.serialno,
    r.psn,
    a.ac_registr,
    rt.psn AS rt_psn,
    DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value",
    a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
    ON UPPER(r.psn) = UPPER(rt.psn)
INNER JOIN amos_postgres.amos.aircraft a
    ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
INNER JOIN (
    SELECT 
        psn,
        MAX(ref_date) AS max_ref_date
    FROM amos_postgres.amos.rotables_trend
    WHERE UPPER(trend_type) = UPPER('CT5')
    GROUP BY psn
) latest_trend
    ON UPPER(rt.psn) = UPPER(latest_trend.psn)
    AND rt.ref_date = latest_trend.max_ref_date
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
    AND r.partno IS NOT NULL
    AND r.serialno IS NOT NULL
    AND r.psn IS NOT NULL
    AND a.ac_registr IS NOT NULL
    AND a.ac_typ IS NOT NULL