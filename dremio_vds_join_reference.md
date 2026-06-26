# Dremio Catalog — VDS Join & Build Reference (`dremio-db`, branch `main`)

**Purpose:** A single reference describing every functional Virtual Dataset (VDS) in the `dremio-db` Arctic catalog (branch `main`) — what each query produces, which tables it reads, and exactly how those tables are joined (join type, keys, filters, grain). It is written to be used when **building new VDSs or modifying existing ones**, so that join keys, grain, and source lineage are never re-reverse-engineered from raw SQL.

**Scope:** All folders under `dremio-db` **except** `Dev` and `source` (raw landing/staging), and excluding `backup`, `testing`, `old_queries`, `dev`, and `test` sub-layers.

| | |
|---|---|
| Catalog | `dremio-db` (Arctic / Nessie, AWS, default CTAS = ICEBERG) |
| Branch | `main` |
| Project ID | `ece53770-82c1-416d-b952-c0e9582fa7b1` |
| Functional VDS count | **228** |
| Generated | 2026-06-16 |
| Owner | DnT Infotech / ASL Data Platform |

> **Status legend:** ✅ = fully documented (join-level) in this revision · 🟡 = inventoried, detailed join documentation pending in a later phase.
> This document is built **in phases** because full join-level documentation of 228 views is large. Revision 1 below contains the complete catalog inventory (all 228) plus full detail for the first 7 folders (13 views). Subsequent revisions append folders without changing the structure.

---

## 1. How to use this document

- **Section 2** is the global convention reference — AMOS epoch date encoding, source path families, and how joins are notated. Read it once; it applies to most views.
- **Section 3** is the complete inventory of all 228 functional views, grouped by folder, with per-view status.
- **Section 4** is the detailed, join-level documentation. Each view entry follows a fixed template: **Purpose → Grain → Source tables → Join map → Filters / business logic → Build/rebuild notes.**
- When **modifying** a view, check its *Grain* and *Join map* first: most defects in this catalog come from a join changing grain (fan-out) or a `LEFT JOIN` silently dropping to `INNER` behaviour via a `WHERE` predicate on the right table.

---

## 2. Global conventions & patterns

These patterns recur across nearly every VDS. They are documented once here and referenced (not repeated) in Section 4.

### 2.1 AMOS epoch date/time encoding
AMOS stores dates and times as integers, **not** native dates:
- **Dates** = *days since `1971-12-31`*. Decoded with `DATE_ADD(DATE '1971-12-31', CAST(<col> AS BIGINT))`.
- **Times** = *minutes since midnight*. Decoded with `FLOOR(<col>/60)` hours + `MOD(<col>,60)` minutes.
- A decoded date equal to `1971-12-31` means the underlying integer was `0` (i.e. NULL/unset) and is treated as empty string in display columns.
- `TO_CHAR(..., 'DD-MM-YYYY')` is the standard display format used by these VDSs.

### 2.2 Source path families
| Path prefix | Meaning |
|---|---|
| `"dremio-db".source.amos.ldg.*` | AMOS maintenance system, **landing** layer (current production source for AMOS VDSs). |
| `"dremio-db".source.amos.stg.*` | AMOS **staging** layer (e.g. `bohi_changes_mat`, `bohi_version_mat`). |
| `"dremio-db".source.hoc.*` | Head-of-Contract (lease management) source. |
| `"dremio-db".source.sap.*` | SAP CDC/Iceberg copy (transaction tables ACDOCA/BKPF/BSEG). |
| `Sap_Prod_Env.SAPABAP1.*` | SAP HANA live source (master/lookup/text tables). |
| `"gedms_prod".gedms.*` | GEDMS MySQL (Cezanne HR, per-diems, etc.). |
| `ASL_INV."debezium-asl".*` | Debezium CDC / output-file CSVs. |
| `"dremio-db".finance.masters.file.*` | Finance master/reference VDSs (cross-domain joins land here). |

> **Migration note:** Many AMOS VDSs still carry commented-out `"dremio-db".Dev."amos_tables".*` paths alongside the live `source.amos.ldg.*` path. These are historical and inert. The active source is always the uncommented `source.amos.*` line.

### 2.3 Join notation used in Section 4
Joins are written as: `LEFT_TABLE  <JOIN TYPE>  RIGHT_TABLE  ON <key(s)>  [+ right-side filter]`.
- **INNER** restricts to matched rows (can drop aircraft/events with no match).
- **LEFT** preserves the left grain; watch for `WHERE` predicates on right-side columns that convert it to effective INNER.
- Sub-select aliases (e.g. `wsl`, `wota`) are pre-filtered/deduplicated inline blocks — the team's established pattern of **pre-filtering before joining** rather than relying on planner pushdown.

### 2.4 Recurring AMOS table glossary
| Table | Grain / role | Common key(s) |
|---|---|---|
| `aircraft` | One row per registration | `ac_registr`, `serialno` |
| `wo_header` | Work order header | `event_perfno_i`, `workorderno_display`, `ac_registr` |
| `forecast` | Forecast maintenance events | `event_perfno_i`, `ac_registr`, `wpno_i` |
| `workstep_link` | Links WO event to work steps | `event_perfno_i`, `workstep_linkno_i`, `descno_i` |
| `wo_text_description` / `wo_text_action` | Work step text/action | `descno_i` / `workstep_linkno_i` |
| `wp_header` / `wp_assignment` | Work package header / assignment | `wpno_i`, `ac_registr` |
| `part` / `part_request_2` | Part master / part requests | `partno` / `event_key` |
| `sign` | Staff/users | `user_sign`, `employee_no_i` |
| `scale` | Dimension descriptions | `SCALE` |
| `moc_daily_records` | MOC daily fault records | `event_perfno_i`, `ac_registr` |

---

## 3. Complete catalog inventory (228 functional views)

### 3.1 Summary by folder

| # | Folder (top level) | Views | Phase-1 status |
|---|---|---|---|
| 1 | `amos_business_continuity` | 3 | ✅ Documented |
| 2 | `amos_training_status_report` | 1 | ✅ Documented |
| 3 | `bi_server` | 34 | 🟡 Pending |
| 4 | `cezanne_emp_directory` | 1 | ✅ Documented |
| 5 | `daily_fleet_status` | 3 | ✅ Documented |
| 6 | `document_status_change` | 4 | 🟡 Pending |
| 7 | `eagle_eye` | 5 | 🟡 Pending |
| 8 | `engine_fleet_status` | 15 | 🟡 Pending |
| 9 | `finance` | 61 | 🟡 Pending |
| 10 | `fleet_mgmt` | 9 | 🟡 Pending |
| 11 | `hoc` | 3 | ✅ Documented |
| 12 | `if_team` | 27 | 🟡 Pending |
| 13 | `incomplete_material_picking` | 1 | ✅ Documented |
| 14 | `intercompany` | 4 | 🟡 Pending |
| 15 | `inventory` | 22 | 🟡 Pending |
| 16 | `maintenance_forecast_alert` | 1 | ✅ Documented |
| 17 | `maintenance_reliability_report` | 4 | 🟡 Pending |
| 18 | `maintenance_reserve` | 14 | 🟡 Pending |
| 19 | `occ` | 10 | 🟡 Pending |
| 20 | `Self_Service` | 6 | 🟡 Pending |
| | **TOTAL** | **228** | |

### 3.2 Full view listing by folder


#### `dremio-db.amos_business_continuity`  (3 views)
- ✅ **`amos_business_continuity`** (3): `forecast`, `history`, `stock`

#### `dremio-db.amos_training_status_report`  (1 views)
- ✅ **`amos_training_status_report`** (1): `amos_training_status_report`

#### `dremio-db.bi_server`  (34 views)
- 🟡 **`bi_server.aims_mm_discrepancy`** (4): `aims_mm_discrepancies`, `aircraft`, `duplicate_mm_leg_id`, `mm_aims_discrepancies`
- 🟡 **`bi_server.bi_views`** (22): `activity_mds_activity`, `flight_leg`, `flight_leg_crew`, `flight_leg_payload`, `flightleg_crew`, `flightleg_delay`, `flightleg_payloadmail`, `leg_crew_pivot`, `leg_delay_pivot`, `v_flightleg_fuel_uplift_retained`, `v_flightleg_pax`, `v_leg_crew_pivot`, `v_leg_delay`, `v_leg_delay_pivot`, `v_leg_mm`, `v_leg_pax`, `v_legmm`, `v_smm_flight_leg`, `v_smm_flightleg`, `v_smm_flightleg_delay`, `v_smm_flightleg_fuel`, `v_smm_flightleg_pax`
- 🟡 **`bi_server.crew_disposition`** (2): `crew_disposition`, `crew_disposition_standby`
- 🟡 **`bi_server.mm_discrepancy`** (6): `missing_actual_times`, `missing_crews`, `missing_customer`, `missing_delay`, `missing_delay_times`, `missing_payload`

#### `dremio-db.cezanne_emp_directory`  (1 views)
- ✅ **`cezanne_emp_directory`** (1): `czuser`

#### `dremio-db.daily_fleet_status`  (3 views)
- ✅ **`daily_fleet_status`** (3): `aog`, `mel`, `scheduled_maintenance`

#### `dremio-db.document_status_change`  (4 views)
- 🟡 **`document_status_change`** (4): `document_status_change`, `document_status_change_accept`, `document_status_change_acceptance`, `document_status_change_prod_1`

#### `dremio-db.eagle_eye`  (5 views)
- 🟡 **`eagle_eye`** (5): `FLIGHTPURPOSE`, `flight_attribute`, `flight_leg`, `flight_leg_delay_reason`, `technical_delay`

#### `dremio-db.engine_fleet_status`  (15 views)
- 🟡 **`engine_fleet_status`** (14): `aircraft_status`, `apu_health`, `bohi_changes`, `egt_cfm`, `egt_cfm_history`, `engine_fleet_status`, `engine_preservation`, `engine_status_historical`, `engine_status_historical_apu`, `engine_status_historical_engine`, `engine_status_historical_storage`, `engine_status_historical_updated`, `forecast_historical`, `togo`
- 🟡 **`engine_fleet_status.ectm`** (1): `ectm_vds`

#### `dremio-db.finance`  (61 views)
- 🟡 **`finance.dashboard_vds`** (15): `asset_cost_center`, `bs_backfill`, `bs_combined`, `bs_final`, `cost_center_master`, `gl_acc_master_at_chart_of_acc_level`, `gl_acc_master_data`, `opening_balance_bs_xero`, `percentage_allocation_master`, `pl_backfill`, `pl_combined`, `pl_final`, `profit_center_master`, `trail_balance_xero_op_bs`, `trail_balance_xero_op_updated`
- 🟡 **`finance.masters.file`** (11): `cost_center_mapping`, `country_entities`, `entity_data_master`, `flash_hierarchy_master`, `master_cmb`, `master_sheet`, `mtce_companies`, `sap_gr_master`, `sap_reporting_category`, `tally_flash_master`, `tcurr_foreign_exchange_master`
- 🟡 **`finance.masters.file.pl_three_entities`** (6): `step1_costcenter`, `step2_gl_account`, `step5_gl_account`, `step6`, `step7`, `step9_step10_step11`
- 🟡 **`finance.sap.bs_vds`** (1): `balance_sheet`
- 🟡 **`finance.sap.pl_vds`** (4): `asl_entities`, `leasing_entity`, `maintenance_entity`, `pl_three_entities`
- 🟡 **`finance.tally`** (4): `bs_query`, `new_combined_P&L_BS`, `pl_query`, `tally_query`
- 🟡 **`finance.xero.bs_vds`** (4): `balance_sheet`, `bs_final_xero`, `foreign_exchange_rates_bs`, `trail_balance_bs`
- 🟡 **`finance.xero.pl_vds`** (2): `foreign_exchange_rates_pl`, `general_ledger_details`
- 🟡 **`finance.xero.tables`** (14): `accounts_asla`, `assets_asla`, `banktransactions_asla`, `banktransfers_asla`, `creditnotes_asla`, `currencies_asla`, `invoices_asla`, `journals_asla`, `manualjournals_asla`, `organisations_asla`, `payments_asla`, `taxrates_asla`, `trackingcategories_asla`, `trialbalances_asla`

#### `dremio-db.fleet_mgmt`  (9 views)
- 🟡 **`fleet_mgmt`** (9): `ac_utilisation`, `aircraft`, `amos_condition`, `aog`, `cfd`, `lease_invoice`, `mr_report`, `rotables`, `rotables_history`

#### `dremio-db.hoc`  (3 views)
- ✅ **`hoc`** (3): `hoc`, `lease_journal_entries`, `schedule`

#### `dremio-db.if_team`  (27 views)
- 🟡 **`if_team`** (27): `activity_mds_activity`, `aviatar_workorder`, `callsign`, `flightleg_crew`, `flightleg_delay`, `flightleg_payloadmail`, `ground_events`, `hptblades_v_leg_mm_5O`, `iqsms_customer`, `mel`, `mel_test`, `odw_ge_v_legs`, `v_dst_bytimezone`, `v_flightleg_fuel_uplift_retained`, `v_flightleg_pax`, `v_leg_crew_pivot`, `v_leg_delay`, `v_leg_delay_pivot`, `v_leg_mm`, `v_leg_mm_5O`, `v_leg_mm_5O_tarmac`, `v_leg_pax`, `v_smm_flightleg`, `v_smm_flightleg_delay`, `v_smm_flightleg_fuel`, `v_smm_flightleg_fuel_receipt`, `v_smm_flightleg_pax`

#### `dremio-db.incomplete_material_picking`  (1 views)
- ✅ **`incomplete_material_picking`** (1): `incomplete_material_picking`

#### `dremio-db.intercompany`  (4 views)
- 🟡 **`intercompany`** (4): `foreign_exchange_eur`, `foreign_exchange_rate_inter`, `foreign_exchange_rates_intercompany`, `intercompany`

#### `dremio-db.inventory`  (22 views)
- 🟡 **`inventory`** (22): `activ_inv`, `all_data`, `combine_data`, `entity_header`, `geo_location`, `measure_unit`, `part`, `previous_month_active_inv`, `previous_month_active_inventory`, `previous_month_activeinv`, `previous_month_alldata`, `s2_previous_month_activeinv_transferred_qty`, `s3_latest_active`, `s3_latest_active_data`, `s7_active_stg`, `s8_active_inv_master`, `s9_date_diff_active_master`, `s9_geo_location`, `s9_test`, `transferred_qty`, `year_month`, `year_months`

#### `dremio-db.maintenance_forecast_alert`  (1 views)
- ✅ **`maintenance_forecast_alert`** (1): `maintenance_forecast_alert`

#### `dremio-db.maintenance_reliability_report`  (4 views)
- 🟡 **`maintenance_reliability_report`** (4): `engine_removals`, `mel`, `unit_removals`, `utilisation`

#### `dremio-db.maintenance_reserve`  (14 views)
- 🟡 **`maintenance_reserve`** (14): `apu_ac_util`, `apu_csn`, `apu_tsn`, `apu_tsn_csn`, `apu_vds`, `engine_latest_status`, `engine_mid_install`, `engine_removal_vds`, `engine_sm_install`, `engine_vds`, `engine_vds_check`, `landing_gear`, `mr_report`, `mr_report_block_hr`

#### `dremio-db.occ`  (10 views)
- 🟡 **`occ`** (10): `aircraft`, `aog`, `aslb_business`, `calender_date`, `cancellation`, `customer_aslb`, `delay`, `flight_leg_latest`, `mel`, `total_sectors`

#### `dremio-db.Self_Service`  (6 views)
- 🟡 **`Self_Service`** (1): `test`
- 🟡 **`Self_Service.dashboard_vds.project.finance`** (5): `BS_FINAL`, `P&L_FINAL`, `entity_data_master`, `foreign_exchange_rate_inter`, `intercompany`

> **Excluded layers (not documented):** `dremio-db.Dev.*`, `dremio-db.source.*`, `bi_server.mm_discrepancy.old_queries` (6), `climate_transition_plan.dev` (1) and `climate_transition_plan.test` (1) — *note: `climate_transition_plan` has **no** production views, only dev/test*, plus `finance.xero.bs_vds.backup` (2) and `finance.xero.bs_vds.testing` (4). `if_team.mel_test` is retained (it sits in a functional folder) but is flagged as a test variant of `if_team.mel`.

---

## 4. Detailed join documentation

> Revision 1 covers folders 1, 2, 4, 5, 11, 13, 16 from the inventory (the standalone and smaller folders). Larger folders (`bi_server`, `engine_fleet_status`, `if_team`, `inventory`, `maintenance_reserve`, `occ`, `finance`, `document_status_change`, `eagle_eye`, `fleet_mgmt`, `intercompany`, `maintenance_reliability_report`, `Self_Service`) are inventoried above and will be appended in subsequent revisions.

---

### 4.1 `dremio-db.amos_business_continuity`

Domain: AMOS maintenance operational continuity — current stock, near-term forecast, recently-closed history. All three read AMOS `ldg`.

#### `amos_business_continuity.stock`  ✅
- **Purpose:** Current physical stock snapshot (consumables + rotables) by location, part, condition and owner.
- **Grain:** One row per `created_date, station, store, location, pn, description, class, repairable, ac_typ, tool, condition, serialno/batch, owner` after `SUM(qty)` aggregation.
- **Source tables:** `source.amos.ldg.consumables`, `source.amos.ldg.rotables`, `source.amos.ldg.part`, `source.amos.ldg.location`.
- **Join map:** Two `UNION ALL` branches, each:
  - `consumables c  INNER  part p  ON c.PARTNO = p.PARTNO`
  - `consumables c  INNER  location l  ON c.LOCATIONNO_I = l.LOCATIONNO_I`
  - (rotables branch identical: `rotables c  INNER  part p ON c.PARTNO=p.PARTNO`; `INNER  location l ON c.LOCATIONNO_I=l.LOCATIONNO_I`)
- **Filters / logic:** No `WHERE`. Rotables `qty` business rule: when `owner NOT IN ('ASLI','ASLB','ASLF') AND locationno_i NOT IN ('-1','-4','-200') AND l.location <> 'INVENTRY'` then `qty=1` else `FA_QTY`. Consumables use raw `QTY`. Outer query `GROUP BY` all dims, `ROUND(SUM(QTY),2)`.
- **Build notes:** `created_date` decoded via §2.1 epoch. To add a column, it must be added to **both** UNION branches **and** the outer `GROUP BY`.

#### `amos_business_continuity.forecast`  ✅
- **Purpose:** Maintenance forecast events **due within the next 7 days** on **open** work orders, with work-package and work-step text/action.
- **Grain:** One row per forecast event (`FO`) passing the date window, enriched with WP + workstep text. `LEFT JOIN`s to text can fan out if a workstep maps to multiple text rows (mitigated by `distinct` inline blocks).
- **Source tables:** `forecast FO`, `wp_header WP`, `wo_header WO`, `workstep_link` (→`wsl`), `wo_text_action` (→`wota`), `wo_text_description` (→`wotd`).
- **Join map:**
  - `forecast FO  LEFT  wp_header WP  ON FO.WPNO_I = WP.WPNO_I`
  - `forecast FO  INNER  wo_header WO  ON FO.EVENT_PERFNO_I = WO.EVENT_PERFNO_I`  *(+ `WO.STATE='O'` in WHERE)*
  - `WO  LEFT  (SELECT DISTINCT event_perfno_i, workstep_linkno_i, descno_i FROM workstep_link) wsl  ON wo.event_perfno_i = wsl.event_perfno_i`
  - `wsl  LEFT  (SELECT DISTINCT workstep_linkno_i, text FROM wo_text_action) wota  ON wsl.WORKSTEP_LINKNO_I = wota.WORKSTEP_LINKNO_I`
  - `wsl  LEFT  (SELECT header, text, text_html, descno_i FROM wo_text_description) wotd  ON wsl.descno_i = wotd.descno_i`
- **Filters / logic:** `CURRENT_DATE() <= expected_date AND expected_date < CURRENT_DATE()+7`; `EXPECTED_DATE >= 0`; `WO.STATE='O'`. `text_html` heavily cleaned via nested `REGEXP_REPLACE` (HTML tags, entities, control chars). `togo` formatting depends on `DIMENSION` (AH/H → h.mm, D/SD → days, C/AC/ID → raw).
- **Build notes:** The `WHERE WO.STATE='O'` makes the `wo_header` join behave as INNER. Dates via §2.1.

#### `amos_business_continuity.history`  ✅
- **Purpose:** Work orders **closed within the last 30 days**, with work/action text and part on/off changes.
- **Grain:** `SELECT DISTINCT` over workorder × workstep × text × action × part-change; filtered to `diff <= 30` days since closing.
- **Source tables:** `wo_header w`, `aircraft a`, `workstep_link wsl`, `wo_text_action wota`, `wo_text_description wotd`, `wo_part_on_off wpnf`.
- **Join map:**
  - `wo_header w  INNER  aircraft a  ON w.AC_REGISTR = a.AC_REGISTR`  *(+ `w.type IN ('M','S','C','P')`)*
  - `(wo)  INNER  workstep_link wsl  ON wo.event_perfno_i = wsl.event_perfno_i`
  - `(wod)  INNER  wo_text_action wota  ON wod.WORKSTEP_LINKNO_I = wota.WORKSTEP_LINKNO_I`
  - `(wod)  INNER  wo_text_description wotd  ON wod.descno_i = wotd.descno_i`
  - `(wod)  LEFT  wo_part_on_off wpnf  ON wod.EVENT_PERFNO_I = wpnf.EVENT_PERFNO_I`
- **Filters / logic:** `diff = EXTRACT(DAY FROM DATE_DIFF(CURRENT_DATE, closing_date)) <= 30`. `STATUS` = decode of `state` (C→Closed, O→Open). `part_changes` is a concatenated string of AC_POSITION + OFF PN/SN + ON PN/SN.
- **Build notes:** `INNER` joins to text mean WOs without workstep text are excluded. Hyphen normalisation (`‐`→`-`) applied to PN/SN.

---

### 4.2 `dremio-db.amos_training_status_report`

#### `amos_training_status_report.amos_training_status_report`  ✅
- **Purpose:** Staff PQS (Personnel Qualification System) training status, enriched with type/class, employee, department and workgroup, plus a certificate-link flag.
- **Grain:** `SELECT DISTINCT` per qualification (`pqs_qualification_no_i`), one row per qualification after left-joining lookups.
- **Source tables (AMOS ldg):** `staff_pqs_qualification Q`, `db_link b`, `staff_pqs_type T`, `staff_pqs_class C`, `sign S`, `department D`, `address add`.
- **Join map:**
  - `Q  LEFT  (SELECT source_pk FROM db_link WHERE source_type='PQSE') b  ON Q.pqs_qualification_no_i = CAST(b.source_pk AS BIGINT)`  → drives `cert_link` (`'Yes'` when matched)
  - `Q  LEFT  staff_pqs_type T  ON Q.pqs_type_no_i = T.pqs_type_no_i`
  - `T  LEFT  staff_pqs_class C  ON T.pqs_class_no_i = C.pqs_class_no_i`
  - `Q  LEFT  sign S  ON Q.employee_no_i = S.employee_no_i`
  - `S  LEFT  department D  ON S.department = D.department`
  - `S  LEFT  address add  ON S.workgroup = add.workgroup`  *(`add.workgroup = UPPER(vendor)`)*
- **Filters / logic:** No active filter (`emp_status`/`status` filters commented out). `issue_date`/`expiry_date` via §2.1 epoch.
- **Build notes:** All enrichment is `LEFT` → qualification rows are always preserved. `cert_link` is a derived existence flag, not a column from `db_link`.

---

### 4.3 `dremio-db.cezanne_emp_directory`

#### `cezanne_emp_directory.czuser`  ✅
- **Purpose:** Cezanne HR employee directory, normalised, with derived AOC entity code.
- **Grain:** One row per `CezanneUser`.
- **Source tables:** `"gedms_prod".gedms.CezanneUser` — **single table, no joins.**
- **Join map:** *(none)*
- **Filters / logic:** Column renames to snake_case; `aoc` derived by `CASE` on `REPLACE(companyNameSearch,'  ',' ')`: ASL Belgium/Gallia→`ASLB`, France→`ASLF`, Ireland→`ASLI`, New Zealand→`ASLNZ`, Australia→`ASLA`, Maintenance France→`ASLMF`, else `Others`.
- **Build notes:** Pure projection/derivation. Safe to extend with more `CezanneUser` columns.

---

### 4.4 `dremio-db.daily_fleet_status`

Domain: Operational daily fleet status dashboards. All read AMOS `ldg`, all anchored on `aircraft` (active, non-COMP).

#### `daily_fleet_status.aog`  ✅
- **Purpose:** Current **AOG** (Aircraft on Ground) events with fault description and outstanding part requests.
- **Grain:** One row per active aircraft × open AOG daily record (matched to forecast/WO/WP), then `LEFT JOIN` to part-request lines (can fan out per part).
- **Source tables:** `aircraft a`, `moc_daily_records m`, `sign s`, `forecast f`, `wo_header w`, `wp_header wp`; part block: `wo_header`, `workstep_link`, `part_request_2`, `part`.
- **Join map (core block):**
  - `(moc_daily_records m  INNER  sign s  ON UPPER(m.CREATED_BY)=UPPER(s.USER_SIGN))`  *(+ `ops_code='AOG' AND solved='N' AND closed='N'`)*
  - `aircraft a  LEFT  m  ON a.ac_registr = m.ac_registr`
  - `a  LEFT  forecast f  ON a.ac_registr=f.ac_registr AND f.event_perfno_i=m.event_perfno_i`
  - `a  LEFT  wo_header w  ON a.ac_registr=w.ac_registr AND m.event_perfno_i=w.event_perfno_i`
  - `a  LEFT  wp_header wp  ON a.ac_registr=wp.ac_registr AND f.wpno_i=wp.wpno_i`
  - outer guard `WHERE z.OPS IS NOT NULL`
- **Join map (part block, outer):**
  - `(wo_header w  INNER  workstep_link wl  ON w.event_perfno_i=wl.event_perfno_i)`
  - `INNER  (part_request_2 pd  INNER  part p  ON pd.partno=p.partno, WHERE pd.event_type='WSL') pr  ON wl.workstep_linkno_i = pr.event_key`
  - `a  LEFT  (part block) b  ON a.Reference_WO = b.event_perfno_i`
- **Filters / logic:** `aircraft status=0 AND AC_REGISTR<>'COMP'`; daily record `ops_code='AOG', solved='N', closed='N'`. `aog_flag` derived; `ground_days = DATEDIFF(today, occurance_date)`; `fault_desc` HTML-cleaned.
- **Build notes:** Multi-column join keys include `ac_registr` redundantly for safety. Part fan-out is expected (one row per outstanding part).

#### `daily_fleet_status.mel`  ✅
- **Purpose:** Open **MEL** (Minimum Equipment List, categories A–D) items per aircraft with forecast TOGO, WO type, and WP schedule window.
- **Grain:** `SELECT DISTINCT` per active aircraft × MEL forecast event.
- **Source tables:** `aircraft a`, `forecast f`, `scale s`, `workstep_link w`, `wo_text_description wt`, `wo_header w` (2nd), `wp_header wp`.
- **Join map:**
  - `(forecast f  INNER  scale s  ON f.DIMENSION = s.SCALE)`
  - `INNER  workstep_link w  ON f.event_perfno_i = w.event_perfno_i`  *(+ `SEQUENCENO='1'`)*
  - `INNER  wo_text_description wt  ON w.DESCNO_I = wt.DESCNO_I`  *(MEL description text)*
  - `aircraft a  LEFT  (f)  ON a.ac_registr = f.ac_registr`
  - `a  LEFT  wo_header w  ON a.ac_registr=f.ac_registr AND f.workorderno_display=w.workorderno_display`  *(+ `state='O' AND type IN ('S','M','P','C')`)*
  - `a  LEFT  wp_header wp  ON a.ac_registr=wp.ac_registr AND f.wpno_i=wp.wpno_i`
- **Filters / logic:** `aircraft status=0, registr<>COMP`; `mel IS NOT NULL` and `mel IN ('A','B','C','D')`. `mel` derived from `SUBSTR(special_flags,4,1)`. TOGO formatted per DIMENSION (§2.4).
- **Build notes:** The inner `f` block is effectively INNER (scale/workstep/text all required), so a forecast with no workstep-1 text won't appear.

#### `daily_fleet_status.scheduled_maintenance`  ✅
- **Purpose:** Scheduled-maintenance work packages with their forecast events, work order, WP assignment, and full station/status/project/priority/approval/address enrichment.
- **Grain:** `SELECT DISTINCT` per active aircraft × forecast event × work package.
- **Source tables (AMOS ldg):** `aircraft a`, `forecast f`, `scale s`, `wo_header wo`, `wp_assignment wp`, `wp_header w`, `station`, `wp_status ws`, `project p`, `wp_priority_codes wpc`, `org_approval op`, `org_auth_config oc`, `address adr1`.
- **Join map:**
  - `(forecast f  INNER  scale s  ON f.DIMENSION = s."SCALE")`
  - `aircraft a  LEFT  (f)  ON a.AC_REGISTR = f.AC_REGISTR`
  - `a  LEFT  wo_header wo  ON a.AC_REGISTR=wo.AC_REGISTR AND f.AC_REGISTR=wo.AC_REGISTR AND f.EVENT_PERFNO_I=wo.EVENT_PERFNO_I AND f.workorderno_display=wo.workorderno_display`  *(+ `wo.STATE='O'`)*
  - `a  LEFT  wp_assignment wp  ON f.WPNO_I=wp.WPNO_I AND f.EVENT_PERFNO_I=wp.EVENT_PERFNO_I`
  - **WP enrichment block `wh`:** `wp_header w  LEFT  station s ON w.STATION=s.STATION`; `INNER wp_status ws ON w.WP_STATUS=ws.WP_STATUS_ID`; `INNER project p ON w.PROJECTNO=p.PROJECTNO`; `INNER wp_priority_codes wpc ON w.PRIORITY_CODE=wpc.TYPE`; `INNER org_approval op ON w.APPROVALNO_I=op.APPROVALNO_I`; `INNER org_auth_config oc ON op.auth_configno_i=oc.auth_configno_i`; `LEFT address adr1 ON op.main_address_i=adr1.address_i`
  - `a  LEFT  (wh)  ON a.AC_REGISTR=wh.AC_REGISTR AND f.AC_REGISTR=wh.AC_REGISTR AND wo.AC_REGISTR=wh.AC_REGISTR AND f.WPNO_I=wh.WPNO_I AND wp.WPNO_I=wh.WPNO_I`
- **Filters / logic:** `aircraft status='0', AC_REGISTR<>'COMP'`; `wo.STATE='O'`. `WP_EST_GROUND_TIME` computed from start/end date+time; `CLASSIFICATION` from `wh.HIDDEN` (L→Line, H→Heavy, I→Hidden).
- **Build notes:** The `wh` block uses several **INNER** joins (wp_status, project, priority, approval, auth_config) — a work package missing any of these reference rows will be dropped from `wh`, leaving WP columns NULL on the outer `LEFT`.

---

### 4.5 `dremio-db.hoc`

Domain: Head-of-Contract lease management. One enrichment VDS + two CSV passthroughs.

#### `hoc.hoc`  ✅
- **Purpose:** Lease contracts joined to branch/entity mapping and lease-accounting amounts (Right-of-Use asset, lease liability, lease receivable) by period.
- **Grain:** `SELECT DISTINCT` per contract × `lease_amount` period row (`period_id/year/month`).
- **Source tables:** `source.hoc.contract c`, `source.hoc.branches b`, `finance.masters.file.entity_data_master ed`, `source.hoc.lease_amount la`.
- **Join map:**
  - `contract c  LEFT  branches b  ON UPPER(c.inputs_department_title) = UPPER(b.name)`
  - `b  LEFT  entity_data_master ed  ON b.custom_sap_code610 = ed."SAP Code"`  *(cross-domain → finance masters)*
  - `c  LEFT  lease_amount la  ON c.id = la.contract`
- **Filters / logic:** None. `entity_code` from `b.custom_sap_code610`; `entity_currency` from `ed."Entity Reporting Currency"`.
- **Build notes:** Cross-domain dependency on `finance.masters.file.entity_data_master` — changes to that master's `SAP Code`/currency columns affect this view. A commented-out earlier version joined branches on `inputs_custom_end_operator54_title` instead of `inputs_department_title`; the **active** key is `inputs_department_title`.

#### `hoc.lease_journal_entries`  ✅
- **Purpose / structure:** Direct passthrough — `SELECT * FROM ASL_INV."debezium-asl".HoC."output_files"."lease_journal_entries.csv"`. **No joins.** Surfaces a pipeline output CSV as a VDS.

#### `hoc.schedule`  ✅
- **Purpose / structure:** Direct passthrough — `SELECT * FROM ASL_INV."debezium-asl".HoC."output_files"."schedule.csv"`. **No joins.**

---

### 4.6 `dremio-db.incomplete_material_picking`

#### `incomplete_material_picking.incomplete_material_picking`  ✅
- **Purpose:** Closed work orders (closing year ≥ 2022) that still have **outstanding part requests** (`confirmed_qty < qty`), enriched with aircraft, and with historical operator/registration resolved from the AMOS BOHI change log.
- **Grain:** One row per WO event × outstanding part (a `ROW_NUMBER()` `index` is assigned), `LEFT JOIN`ed to operator-change history.
- **Source tables:** `wo_header wh`, `workstep_link wsl`, `part_request_2 pr`, `aircraft a`; history block: `aircraft a`, `source.amos.stg.bohi_changes_mat bc`, `source.amos.stg.bohi_version_mat bv`.
- **Join map (core):**
  - `wo_header wh  INNER  workstep_link wsl  ON wh.event_perfno_i = wsl.event_perfno_i`  *(wh `state='C'`, `years>=2022`)*
  - `INNER  (part_request_2 pr WHERE event_type='WSL' AND status=2 AND outstanding_parts<>'N') pr  ON wsl.workstep_linkno_i = pr.event_key`
  - `INNER  aircraft a  ON wh.ac_registr = a.ac_registr`
- **Join map (history, outer):**
  - `aircraft a  INNER  (bohi_changes_mat bc WHERE CHANGES LIKE '%OPERATOR%'  INNER  bohi_version_mat bv ON bc.VERSIONNO_I=bv.VERSIONNO_I) b  ON a.SERIALNO = b.OLD_SERIALNO`
  - `(core) a  LEFT  (history) b  ON a.SERIALNO = b.SERIALNO`
- **Filters / logic:** `wh.state='C'`, `closing_date`/`issue_date NOT NULL`, `years>=2022`; part `status=2 (Event Closed)` and `confirmed_qty < qty`. `ac_registr`/`entity` chosen by comparing `issue_date` vs `b.CHANGE_DATE` (use historical operator/reg if the WO predates the change). Operator strings parsed out of `CHANGES` HTML via `REGEXP_REPLACE` + `SUBSTRING_INDEX`.
- **Build notes:** BOHI tables migrated from `Dev` to `source.amos.stg` (`bohi_changes_mat`, `bohi_version_mat`). `target` is a hardcoded constant `250`.

---

### 4.7 `dremio-db.maintenance_forecast_alert`

#### `maintenance_forecast_alert.maintenance_forecast_alert`  ✅
- **Purpose:** Overdue / unplanned forecast events (past expected date, **no** planned date) for **managed** aircraft, with a 7-column remarks pivot and an include/exclude classification.
- **Grain:** One row per managed aircraft × overdue forecast event.
- **Source tables (CTE-based):** `aircraft` (→`aircraft_data`), `wo_remarks` (→`remarks_data`, pivoted), `wo_header` (→`open_workorders`), `forecast` (→`forecast_data`).
- **Join map:**
  - `forecast f  INNER  open_workorders w  ON f.event_perfno_i = w.event_perfno_i`  *(open WO = `state NOT IN ('C')`)*
  - `f  LEFT  remarks_data r  ON f.event_perfno_i = r.event_perfno_i`
  - **final:** `aircraft_data a  INNER  filtered_forecast f  ON a.ac_registr = f.ac_registr`
- **Filters / logic:** `aircraft status=0 AND registr<>'COMP' AND non_managed='N'`; forecast `event_type IN ('D','R','C','V','T','Q')`; `filtered_forecast`: `curr_date >= expected_dt AND planned_date IS NULL AND expected_dt >= CURRENT_DATE-3`. `included_excluded` = `'EXCLUDED'` for `ac_typ='A330'` or a hardcoded registration list, else `'INCLUDED'`. `remarks_data` pivots `wo_remarks.recno` 1–7 into `c1..c7` via `MAX(CASE...)`.
- **Build notes:** The hardcoded EXCLUDED registration list is maintenance-sensitive (update when fleet changes). Remarks pivot caps at 7 — extend the `CASE` set if more remark lines are needed.

---

## 5. Revision log & next phases

| Revision | Contents |
|---|---|
| **R1 (this file)** | Conventions (§2) · full 228-view inventory (§3) · join-level detail for `amos_business_continuity`, `amos_training_status_report`, `cezanne_emp_directory`, `daily_fleet_status`, `hoc`, `incomplete_material_picking`, `maintenance_forecast_alert` (13 views). |
| R2 (planned) | `document_status_change` (4, large), `eagle_eye` (5), `intercompany` (4), `maintenance_reliability_report` (4), `Self_Service` (6). |
| R3 (planned) | `fleet_mgmt` (9), `occ` (10), `engine_fleet_status` (15). |
| R4 (planned) | `bi_server` (34), `if_team` (27). |
| R5 (planned) | `inventory` (22), `maintenance_reserve` (14). |
| R6 (planned) | `finance` (61, across 9 subfolders). |

**Suggested processing order rationale:** smallest/standalone first (done), then mid-size operational domains, then the large flight-leg/BI families (`bi_server`/`if_team` share many `v_leg_*`/`v_smm_*` view names and should be documented together to capture shared lineage), then the multi-step `inventory` and `maintenance_reserve` pipelines, then `finance` last (largest, most cross-domain, depends on SAP + Xero + Tally + masters already understood).


---

### Created via workflow — 2026-06-22 11:26 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health metrics for ASL B737NG aircraft using latest CT5ATP trend data.
- **Grain:** One row per APU PSN with most recent reference date.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables r  INNER JOIN  latest_apu_trends lat  ON r.psn = lat.psn AND lat.rn = 1
  - rotables r  INNER JOIN  aircraft a  ON UPPER(r.ac_registr) = UPPER(a.ac_registr) AND UPPER(a.ac_typ) = UPPER('B737NG')
- **Filters / logic:** Trend type filtered to 'CT5' (case-insensitive); aircraft type restricted to B737NG; row number window function selects latest trend per PSN by ref_date descending; ref_date converted from epoch offset (1971-12-31 base).
- **Build notes:** Case-insensitive comparisons applied to trend_type and ac_typ for robustness; ref_date calculation uses DATE_ADD with epoch base—verify offset if source schema changes; PSN is the unique identifier for rotable parts; consider indexing on psn and ref_date in source tables for performance.


---

### Created via workflow — 2026-06-22 11:38 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health for B737NG aircraft by combining APU rotable component data with the latest CT5 ATP trend values.
- **Grain:** One row per APU serial number (latest CT5 ATP value by reference date).
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables r  INNER JOIN  trend_ranked tr  ON r.psn = tr.psn AND tr.rn = 1
  - rotables r  INNER JOIN  aircraft ac  ON UPPER(r.ac_registr) = UPPER(ac.ac_registr) AND UPPER(ac.ac_typ) = 'B737NG'
- **Filters / logic:** Trend type = 'CT5', trend status = 1, aircraft type = 'B737NG'; ROW_NUMBER window ranks trends by PSN descending on ref_date to isolate latest value.
- **Build notes:** ref_date is stored as days offset from 1971-12-31 and must be converted using DATE_ADD. Case-insensitive matching applied to ac_registr and ac_typ. Latest modified 2026-06-16.


---

### Created via workflow — 2026-06-22 21:52 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health for B737NG aircraft by extracting the latest CT5ATP trend values.
- **Grain:** One row per APU PSN with its most recent reference date.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables (r)  INNER JOIN  aircraft (a)  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
  - rotables (r)  INNER JOIN  rotables_trend (rt)  ON r.psn = rt.psn
  - rotables_trend (rt)  INNER JOIN  latest_apu_trends (lat)  ON rt.psn = lat.psn AND rt.ref_date = lat.max_ref_date
- **Filters / logic:** Aircraft type filtered to B737NG; trend type filtered to CT5; CTE `latest_apu_trends` ensures only the maximum reference date per PSN is returned; ref_date converted from epoch integer (1971-12-31 baseline) to calendar date.
- **Build notes:** Epoch conversion uses DATE_ADD with 1971-12-31 baseline; case-insensitive comparisons applied to all string filters; PSN is the unique identifier for rotable equipment; future modifications should preserve the MAX(ref_date) logic to maintain latest-value semantics.


---

### Created via workflow — 2026-06-22 22:24 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health for B737NG aircraft by joining APU rotable parts with latest CT5 trend data.
- **Grain:** One row per APU (PSN) with the most recent CT5 reference date.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables (r)  INNER JOIN  trend_latest (t)  ON r.psn = t.psn AND t.rn = 1
  - rotables (r)  LEFT JOIN  aircraft (a)  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
- **Filters / logic:** Trend type = 'CT5', ref_date > 0, aircraft type = 'B737NG'; ROW_NUMBER() window function selects latest trend record per PSN; ref_date converted from epoch offset (1971-12-31 base).
- **Build notes:** CT5 trend filtering occurs in CTE before join to optimize performance; aircraft join is LEFT to preserve APU records with missing aircraft metadata; all registration and aircraft type comparisons use UPPER() for case-insensitive matching.


---

### Created via workflow — 2026-06-23 05:23 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health for B737NG aircraft by displaying the latest CT5 trend data per APU.
- **Grain:** One row per APU PSN with the most recent CT5 reference date.
- **Source tables:** amos_postgres.amos.rotables_trend, amos_postgres.amos.rotables, amos_postgres.amos.aircraft
- **Join map:**
  - latest_ct5_trends lct  INNER JOIN  rotables r  ON lct.psn = r.psn
  - rotables r  INNER JOIN  aircraft ac  ON UPPER(r.ac_registr) = UPPER(ac.ac_registr)
- **Filters / logic:** CT5 trend type only; aircraft type filtered to B737NG; ROW_NUMBER window function selects latest ref_date per PSN (rn = 1); case-insensitive aircraft registration matching.
- **Build notes:** ref_date is stored as days since 1971-12-31 and requires DATE_ADD conversion; all string comparisons use UPPER() for consistency; PSN is the unique APU identifier; future modifications should preserve the window function logic to maintain "latest" semantics.


---

### Created via workflow — 2026-06-23 06:14 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health for B737NG aircraft by extracting the latest APU performance data (CT5 trend type) from AMOS.
- **Grain:** One row per APU (rotable) per aircraft registration, showing the most recent trend reference date.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables r  INNER JOIN  aircraft a  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
  - rotables r  LEFT JOIN  rotables_trend atr  ON r.psn = atr.psn AND atr.rn = 1 (ranked by ref_date DESC)
- **Filters / logic:** Aircraft type = 'B737NG'; trend type = 'CT5'; ac_registr IS NOT NULL; window function ranks trends by ref_date descending per PSN, selecting only the latest (rn = 1).
- **Build notes:** ref_date is calculated from days since 1971-12-31 epoch; event_perfno_i may be NULL; CT5 represents APU compressor discharge temperature; modifications to trend_type filter or aircraft type require updates to WHERE clause and CTE logic.


---

### Created via workflow — 2026-06-23 09:20 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Retrieves APU performance data from AMOS for B737NG aircraft, displaying the latest CT5 trend record per APU.
- **Grain:** One row per APU (PSN) with the most recent CT5 trend measurement.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables (r)  INNER JOIN  rotables_trend (rt)  ON r.psn = rt.psn
  - rotables (r)  INNER JOIN  aircraft (a)  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
- **Filters / logic:** Trend type = 'CT5'; Aircraft type = 'B737NG'; ROW_NUMBER ranking retains only the latest ref_date per PSN; ref_date converted from epoch offset (1971-12-31 base).
- **Build notes:** Case-insensitive matching applied to trend_type and ac_typ. ref_date calculation uses DATE_ADD with epoch base of 1971-12-31. Future modifications should preserve the ranking window to maintain single-row-per-PSN grain.


---

### Created via workflow — 2026-06-25 06:27 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health for ASL B737NG aircraft by retrieving the latest CT5 ATP trend data per APU.
- **Grain:** One row per APU (unique psn), showing the most recent CT5 ATP trend record.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables r  INNER JOIN  rotables_trend rt  ON r.psn = rt.psn
  - rotables_trend rt  INNER JOIN  latest_trend lt  ON rt.psn = lt.psn AND rt.ref_date = lt.max_ref_date
  - rotables r  INNER JOIN  aircraft ac  ON UPPER(r.ac_registr) = UPPER(ac.ac_registr)
- **Filters / logic:** Trend type = 'CT5', aircraft type = 'B737NG', ref_date > 0; CTE `latest_trend` identifies maximum ref_date per psn to ensure one row per APU.
- **Build notes:** ref_date is stored as days since 1971-12-31 and converted using DATE_ADD; case-insensitive matching on ac_registr and ac_typ; event_perfno_i may be NULL.


---

### Created via workflow — 2026-06-25 06:35 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health for ASL B737NG aircraft by retrieving latest CT5 trend data.
- **Grain:** One row per APU serial number (psn) with latest reference date.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables (r)  INNER JOIN  rotables_trend (rt)  ON r.psn = rt.psn
  - rotables (r)  INNER JOIN  aircraft (a)  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
- **Filters / logic:** Trend type = 'CT5', aircraft type = 'B737NG', ref_date > 0; QUALIFY clause ensures only the most recent trend record per PSN is returned.
- **Build notes:** Date conversion uses epoch offset (1971-12-31) for ref_date; UPPER() applied to string comparisons for case-insensitive matching; subquery validates existence of ranked records before QUALIFY filtering; ref_date must be positive to exclude invalid epoch values.


---

### Created via workflow — 2026-06-25 06:48 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Retrieve APU performance data for B737NG aircraft with latest CT5ATP trend values.
- **Grain:** One row per APU (PSN) with most recent trend record.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables (r)  LEFT JOIN  aircraft (a)  ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
  - rotables (r)  LEFT JOIN  rotables_trend (rt)  ON r.psn = rt.psn AND rt.trend_type = 'CT5'
- **Filters / logic:** Aircraft type filtered to B737NG (case-insensitive); trend type restricted to CT5; ROW_NUMBER() ranks trends by ref_date descending per PSN, selecting only most recent (rn = 1).
- **Build notes:** ref_date is converted from integer offset days since 1971-12-31; duplicate trend_type filter in WHERE clause is redundant with JOIN condition; LEFT JOINs may produce nulls if aircraft or trend records missing.


---

### Created via workflow — 2026-06-26 09:26 UTC  (ADL-1700)

#### `dremio-db.apu_health.apu_health`  ✅
- **Purpose:** Monitor APU health for B737NG aircraft by extracting the latest CT5 ATP trend values for performance tracking.
- **Grain:** One row per APU (unique PSN) with its most recent CT5 ATP performance metric.
- **Source tables:** amos_postgres.amos.rotables, amos_postgres.amos.rotables_trend, amos_postgres.amos.aircraft
- **Join map:**
  - rotables r  INNER JOIN  rotables_trend rt  ON r.psn = rt.psn
  - rotables_with_rn rwr  INNER JOIN  aircraft a  ON UPPER(rwr.ac_registr) = UPPER(a.ac_registr)
- **Filters / logic:** Excludes null aircraft registrations; filters to CT5 trend type only; selects most recent trend per PSN using ROW_NUMBER(); limits to B737NG aircraft type; ref_date converted from AMOS epoch (1971-12-31).
- **Build notes:** ROW_NUMBER() window function requires ordered ref_date DESC to capture latest trend; case-insensitive aircraft registration matching; ref_date conversion uses AMOS epoch baseline; PSN is the unique rotable identifier.
