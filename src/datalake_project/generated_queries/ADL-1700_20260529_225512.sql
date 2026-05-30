-- VDS: APU Health Monitor
-- Purpose: Extract APU performance data from AMOS for B737NG aircraft
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Owner: ASL Airlines
-- Ticket: ADL-1700

SELECT
    r.partno,
    r.serialno,
    r.psn,
    a.ac_registr,
    DATE_ADD(DATE '1971-12-31', CAST(rt.ref_date AS BIGINT)) AS ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value",
    ac.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
    ON UPPER(r.psn) = UPPER(rt.psn)
INNER JOIN amos_postgres.amos.aircraft ac
    ON UPPER(a.ac_registr) = UPPER(ac.ac_registr)
INNER JOIN (
    SELECT
        psn,
        MAX(ref_date) AS max_ref_date
    FROM amos_postgres.amos.rotables_trend
    WHERE trend_type = 'CT5'
    GROUP BY psn
) latest
    ON UPPER(rt.psn) = UPPER(latest.psn)
    AND rt.ref_date = latest.max_ref_date
WHERE UPPER(ac.ac_typ) = UPPER('B737NG')
    AND rt.trend_type = 'CT5'