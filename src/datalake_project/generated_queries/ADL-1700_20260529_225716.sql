-- VDS: APU Health Monitor - B737NG Fleet
-- Source: AMOS Acceptance
-- Purpose: Extract APU performance data (CT5 trend metrics) for B737NG aircraft
-- Last Updated: ADL-1700
-- Owner: Engine Folder

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
) latest
    ON UPPER(rt.psn) = UPPER(latest.psn)
    AND rt.ref_date = latest.max_ref_date
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')