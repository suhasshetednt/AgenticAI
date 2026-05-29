-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5 trend values
-- Source: amos_postgres.amos (AMOS Acceptance)
-- Owner: Engine Folder
-- Ticket: ADL-1700

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
    ) latest
        ON UPPER(rt.psn) = UPPER(latest.psn)
        AND rt.ref_date = latest.max_ref_date
WHERE
    UPPER(ac.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
ORDER BY
    ac.ac_registr,
    r.psn,
    rt.ref_date DESC