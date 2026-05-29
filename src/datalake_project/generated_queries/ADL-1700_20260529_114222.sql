-- VDS: APU Health Monitor - B737NG Fleet
-- Source: AMOS Acceptance
-- Purpose: Extract APU performance data (CT5 trends) for B737NG aircraft
-- Last Updated: ADL-1700

SELECT
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
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
    AND rt.ref_date = (
        SELECT MAX(rt2.ref_date)
        FROM amos_postgres.amos.rotables_trend rt2
        WHERE UPPER(rt2.psn) = UPPER(r.psn)
            AND UPPER(rt2.trend_type) = UPPER('CT5')
    )