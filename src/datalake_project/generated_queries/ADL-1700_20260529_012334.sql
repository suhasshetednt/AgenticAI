-- VDS: amos_maintenance_apu_health_monitor_vds
-- Jira: ADL-1700
-- Src: amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
-- Desc: Retrieve APU performance data for B737NG aircraft with latest CT5 trend values

WITH latest_trend AS (
    SELECT 
        psn,
        ref_date,
        trend_type,
        event_perfno_i,
        "value",
        ROW_NUMBER() OVER (PARTITION BY UPPER(psn) ORDER BY ref_date DESC) as rn
    FROM amos_postgres.amos.rotables_trend
    WHERE UPPER(trend_type) = UPPER('CT5')
)
SELECT
    r.partno,
    r.serialno,
    r.psn,
    ac.ac_registr,
    DATE_ADD(DATE '1971-12-31', CAST(lt.ref_date AS BIGINT)) AS ref_date,
    lt.trend_type,
    lt.event_perfno_i,
    lt."value",
    ac.ac_typ
FROM amos_postgres.amos.rotables r
INNER JOIN amos_postgres.amos.aircraft ac
    ON UPPER(r.ac_registr) = UPPER(ac.ac_registr)
INNER JOIN latest_trend lt
    ON UPPER(r.psn) = UPPER(lt.psn)
WHERE UPPER(ac.ac_typ) = UPPER('B737NG')
  AND lt.rn = 1