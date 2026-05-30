-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5 trend values
-- Source: AMOS (amos_postgres.amos.*)
-- Owner: Engine Folder
-- Last Updated: ADL-1700

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
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
    AND (r.psn, rt.ref_date) IN (
        SELECT r2.psn, MAX(rt2.ref_date)
        FROM amos_postgres.amos.rotables r2
        INNER JOIN amos_postgres.amos.rotables_trend rt2
            ON UPPER(r2.psn) = UPPER(rt2.psn)
        INNER JOIN amos_postgres.amos.aircraft a2
            ON UPPER(r2.ac_registr) = UPPER(a2.ac_registr)
        WHERE UPPER(a2.ac_typ) = UPPER('B737NG')
            AND UPPER(rt2.trend_type) = UPPER('CT5')
        GROUP BY r2.psn
    )