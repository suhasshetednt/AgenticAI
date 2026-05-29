-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft with latest CT5ATP trend values
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Folder: Engine
-- Last Updated: ADL-1700

SELECT
    r.partno,
    r.serialno,
    r.psn,
    ac.ac_registr,
    DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
    rt.trend_type,
    COALESCE(rt.event_perfno_i, '') AS event_perfno_i,
    rt."value",
    ac.ac_typ
FROM
    amos_postgres.amos.rotables r
    INNER JOIN amos_postgres.amos.rotables_trend rt
        ON UPPER(r.psn) = UPPER(rt.psn)
    INNER JOIN amos_postgres.amos.aircraft ac
        ON UPPER(r.ac_registr) = UPPER(ac.ac_registr)
WHERE
    UPPER(ac.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
    AND rt.ref_date = (
        SELECT MAX(rt2.ref_date)
        FROM amos_postgres.amos.rotables_trend rt2
        WHERE UPPER(rt2.psn) = UPPER(r.psn)
            AND UPPER(rt2.trend_type) = UPPER('CT5')
    )