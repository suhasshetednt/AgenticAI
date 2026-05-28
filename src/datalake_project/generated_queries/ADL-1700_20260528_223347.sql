-- VDS: APU Health Monitor
-- Folder: Engine
-- Source: amos_postgres.amos (AMOS Acceptance)
-- Purpose: Monitor APU health metrics (CT5ATP trends) for B737NG aircraft
-- Last Updated: ADL-1700

SELECT
    r.partno,
    r.serialno,
    r.psn,
    UPPER(a.ac_registr) AS ac_registr,
    UPPER(a.ac_typ) AS ac_typ,
    DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value"
FROM
    amos_postgres.amos.rotables r
    INNER JOIN amos_postgres.amos.rotables_trend rt
        ON UPPER(r.psn) = UPPER(rt.psn)
    INNER JOIN amos_postgres.amos.aircraft a
        ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
    INNER JOIN (
        SELECT
            psn,
            MAX(ref_date) AS max_ref_date
        FROM
            amos_postgres.amos.rotables_trend
        WHERE
            UPPER(trend_type) = UPPER('CT5')
        GROUP BY
            psn
    ) rt_max
        ON UPPER(rt.psn) = UPPER(rt_max.psn)
        AND rt.ref_date = rt_max.max_ref_date
WHERE
    UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')