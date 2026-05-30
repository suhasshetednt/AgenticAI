-- VDS: APU Health Monitor
-- Description: APU performance data from AMOS for B737NG aircraft, latest reference date per APU
-- Source: amos_postgres.amos (rotables, rotables_trend, aircraft)
-- Owner: ASL Airlines
-- Ticket: ADL-1700

SELECT
    r.partno,
    r.serialno,
    r.psn,
    a.ac_registr,
    rt.ref_date,
    rt.trend_type,
    rt.event_perfno_i,
    rt."value",
    a.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.rotables_trend rt
    ON r.psn = rt.psn
INNER JOIN amos_postgres.amos.aircraft a
    ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
WHERE UPPER(a.ac_typ) = UPPER('B737NG')
    AND UPPER(rt.trend_type) = UPPER('CT5')
    AND rt.ref_date = (
        SELECT MAX(rt2.ref_date)
        FROM amos_postgres.amos.rotables_trend rt2
        WHERE rt2.psn = rt.psn
    )