-- VDS: APU Health Monitor
-- Description: APU performance data for B737NG aircraft with latest CT5 trend values
-- Source: AMOS (amos_postgres.amos.*)
-- Last Updated: ADL-1700
-- Dependencies: rotables, rotables_trend, aircraft tables

SELECT
    r.partno,
    r.serialno,
    r.psn,
    a.ac_registr,
    DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
    rt.trend_type,
    COALESCE(rt.event_perfno_i, '') AS event_perfno_i,
    rt."value",
    a.ac_typ
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
            trend_type = 'CT5'
        GROUP BY
            psn
    ) latest
        ON UPPER(rt.psn) = UPPER(latest.psn)
        AND rt.ref_date = latest.max_ref_date
WHERE
    UPPER(a.ac_typ) = UPPER('B737NG')
    AND rt.trend_type = 'CT5'