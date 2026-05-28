# Dremio Query Rules — ASL Airlines Data Lake

These rules MUST be followed every time a SQL query or VDS is written.
Read all rules before generating any query.

---

## 1. AMOS Data Patterns (Always Apply)

### 1.1 Date Conversion
AMOS stores dates as integers (days since 1971-12-31). Always convert:
```sql
DATE_ADD(DATE '1971-12-31', CAST(<date_field> AS BIGINT)) AS <alias>
```
Never expose raw integer date fields without conversion.

### 1.2 Certificate Link Indicator
Always use LEFT JOIN on `db_link` and derive the indicator:
```sql
LEFT JOIN amos_postgres.amos.db_link b
    ON  b.source_pk   = q.<pk_field>
    AND b.source_type = '<SOURCE_TYPE>'   -- e.g. 'PQSE'

CASE WHEN b.source_pk IS NULL THEN 'No' ELSE 'Yes' END AS cert_link
```

### 1.3 Null Handling (COALESCE / NULLIF)
When applying functions to handle nulls (like `COALESCE` or `NULLIF`), the fallback/replacement value MUST strictly match the column's data type.

**Crucial Rule:** 
If the column type is **character or varchar**, then only it should use `''` (empty string). 
For **all other data types** (integer, numeric, double, date, etc.), it should be `NULL`.

| Column type | Correct Usage | Wrong |
|---|---|---|
| VARCHAR / CHAR / TEXT | `COALESCE(col, '')` / `NULLIF(col, '')` | `COALESCE(col, NULL)` |
| INTEGER / DOUBLE / NUMERIC | `COALESCE(col, NULL)` or `NULLIF(col, 0)` | `COALESCE(col, '')` / `NULLIF(col, '')` — causes "invalid input syntax" |
| DATE / TIMESTAMP | `COALESCE(col, NULL)` | `COALESCE(col, '')` |

```sql
-- VARCHAR column (department, workgroup, code fields):
COALESCE(d.department, '')  AS department
NULLIF(d.workgroup, '')     AS workgroup

-- Numeric / Date column (value, quantity, date):
COALESCE(rt."value", NULL)  AS "value"
```

**Always call `search_catalog()` to check the column type before applying COALESCE or NULLIF.**

### 1.4 Workgroup Join
Always UPPER() the workgroup value before joining with the address table:
```sql
LEFT JOIN amos_postgres.amos.address a
    ON a.workgroup = UPPER(NULLIF(d.workgroup, ''))
```

### 1.5 db_link Filtering
Always filter the `db_link` table by `source_type` to avoid cross-joining all link types:
```sql
WHERE b.source_type = '<SOURCE_TYPE>'
-- or use ON clause for LEFT JOINs (preferred)
```

### 1.6 AMOS Source Consistency (CRITICAL)
When ANY table in the query comes from AMOS, ALL tables in the query MUST also come
from `amos_postgres.amos.*`. Never mix AMOS tables with Movement Manager (`mm.table`),
SAP, Xero, or any other source unless the ticket explicitly requires a cross-source join.

**Wrong — mixing AMOS and Movement Manager:**
```sql
JOIN amos_postgres.amos.rotables r ON ...
JOIN mm.aircraft a ON r.ac_registr = a.tail_number   -- WRONG: MM aircraft
```

**Correct — all AMOS:**
```sql
JOIN amos_postgres.amos.rotables r ON ...
JOIN amos_postgres.amos.aircraft a ON r.ac_registr = a.ac_registr   -- correct: AMOS aircraft
```

**AMOS vs MM source disambiguation — mandatory for all joins:**

| Table need | AMOS source (all AMOS queries) | MM source (only MM queries) |
|---|---|---|
| Aircraft master | `amos_postgres.amos.aircraft` — join on **`ac_registr`** | `mm.aircraft` — join on **`tail_number`** |
| Airport | `amos_postgres.amos.airport` | `mm.airport` |
| Crew / Staff | `amos_postgres.amos.staff` | `mm.crew` |

> **`tail_number` NEVER appears in an AMOS query.** If the LLM or catalog suggests
> `aircraft.tail_number` while any other table is `amos_postgres.amos.*`, it is wrong.
> The auto-fix in `_fix_dremio_sql()` converts `alias.tail_number → alias.ac_registr`
> whenever the SQL contains `amos_postgres.amos.` — but this must be caught at generation time.

**AMOS `aircraft` known columns (catalog entry is from MM — use these instead):**
```
ac_registr  VARCHAR  — aircraft registration, primary join key
ac_typ      VARCHAR  — aircraft type (e.g. B737NG, B737MAX)
```

When in doubt, call `search_catalog('aircraft')` and check the `domain` column — `amos.tables`
means AMOS source, `mm.table` means Movement Manager.

### 1.7 Case-Insensitive String Comparisons (CRITICAL)
AMOS stores string values (aircraft type, registration, codes) in inconsistent case.
Always wrap **both sides** of a string equality comparison in `UPPER()` to guarantee correct results.

**Wrong — case-sensitive, may miss rows:**
```sql
WHERE a.ac_typ = 'B737NG'
WHERE r.ac_registr = 'A6-FEA'
WHERE p.part_no = 'abc-123'
```

**Correct — both sides UPPER:**
```sql
WHERE UPPER(a.ac_typ)     = UPPER('B737NG')
WHERE UPPER(r.ac_registr) = UPPER('A6-FEA')
WHERE UPPER(p.part_no)    = UPPER('abc-123')
```

This also applies to JOIN conditions on string keys:
```sql
-- Wrong:
ON r.ac_registr = a.ac_registr

-- Correct:
ON UPPER(r.ac_registr) = UPPER(a.ac_registr)
```

Exception: numeric columns, date integers, and boolean fields — do NOT wrap these in UPPER().

### 1.8 Common AMOS Table Column Mappings (CRITICAL)
When querying key AMOS tables, ensure you use the exact catalog column names. The agent/LLM often guesses standard abbreviations which causes validation errors:

| Table | Concept | Correct Column Name | Common Wrong Guesses |
|---|---|---|---|
| `amos_postgres.amos.rotables` | Part Number | `partno` | `pn`, `part_no`, `part_number` |
| `amos_postgres.amos.rotables` | Serial Number | `serialno` | `sn`, `serial_no`, `serial_number` |
| `amos_postgres.amos.rotables` | Part Serial Number | `psn` | `psn_no`, `rot_psn` |

Never use `pn`, `sn`, `part_no`, or `serial_no` for `rotables` columns — Dremio will fail validation instantly with "Column not found".

---

## 2. Query Structure & Optimisation

### 2.1 SELECT Columns
- Never use `SELECT *` in VDS definitions — list all columns explicitly.
- Always alias computed columns with meaningful names.
- Group columns logically: IDs → descriptive text → dates → flags/indicators.

### 2.2 DISTINCT
- Use `SELECT DISTINCT` when joining dimension tables (department, address) that can cause fan-out duplication.
- Do NOT use DISTINCT when aggregating — it is redundant and hides bugs.

### 2.3 JOIN Type Selection
| Scenario | JOIN Type |
|---|---|
| Lookup that may not exist (cert_link, dept) | LEFT JOIN |
| Mandatory relationship (type, class) | LEFT JOIN (still — AMOS data can be dirty) |
| Many-to-many risk | Add DISTINCT or aggregate |
| Never use | CROSS JOIN, RIGHT JOIN |

### 2.4 Filter Pushdown
- Apply WHERE filters as early as possible — on the base table, not after joins.
- Never filter on a joined column when the same filter can go on the source table.

### 2.5 NULL Handling
- Use `COALESCE(<col>, <default>)` when a NULL would break downstream logic.
- Use `NULLIF(<col>, 0)` to avoid division-by-zero in ratio calculations.

### 2.6 Date Range Filters
When filtering on converted AMOS dates, convert the filter value too — do not compare converted dates against raw integers:
```sql
WHERE DATE_ADD(DATE '1971-12-31', CAST(q.expiry_date AS BIGINT)) >= CURRENT_DATE
```

---

## 3. Dremio-Specific SQL Rules

### 3.1 Quoting Identifiers
- Always use double quotes for identifiers with hyphens or mixed case:
  `"dremio-db"."folder_name"."view_name"`
- Use no quotes for simple lowercase identifiers in CTEs or aliases.

### 3.1a Reserved Keyword Quoting (MANDATORY — query will fail without this)
Dremio SQL reserves many common words. Using them as bare column names causes
immediate parse errors. **Before writing any query, call search_catalog() to get
the column list, then scan every column name against this table.**

Any column name that matches a reserved word MUST be wrapped in double quotes
**at every single occurrence** in the query: SELECT, FROM alias, WHERE, GROUP BY,
ORDER BY, JOIN ON, and inside CTEs.

| Reserved word | Quoted form |
|---|---|
| `value` / `values` | `rt."value"` / `AS "value"` |
| `timestamp` | `t."timestamp"` / `AS "timestamp"` |
| `date` | `r."date"` / `AS "date"` |
| `time` | `r."time"` / `AS "time"` |
| `interval` | `r."interval"` |
| `type` | `r."type"` / `AS "type"` |
| `status` | `r."status"` / `AS "status"` |
| `end` | `r."end"` / `AS "end"` |
| `start` | `r."start"` / `AS "start"` |
| `key` | `r."key"` / `AS "key"` |
| `level` | `r."level"` |
| `row` / `rows` | `r."row"` |
| `rank` | `r."rank"` |
| `position` | `r."position"` |
| `year` / `month` / `day` / `hour` / `minute` / `second` | quote when used as column names |
| `percent` | `r."percent"` |
| `group` | `r."group"` |
| `order` | `r."order"` |
| `table` | `r."table"` |

**Wrong — query will fail at parse time:**
```sql
SELECT rt.value AS value         -- parse error: value is reserved
WHERE rt.type = 'CT5'            -- parse error: type is reserved
GROUP BY rt.value                -- parse error
```
**Correct — every occurrence quoted:**
```sql
SELECT rt."value" AS "value"
WHERE rt."type" = 'CT5'
GROUP BY rt."value"
```

**Checklist before submitting any query:**
1. Get column names via `search_catalog(table_name)`
2. For each column: if it appears in the reserved-word table above → quote it everywhere
3. Also quote the alias in `AS "value"` — not just the column reference

### 3.2 Data Types
- Cast numeric AMOS dates to BIGINT before DATE_ADD: `CAST(<field> AS BIGINT)`
- Cast INTEGER status codes to VARCHAR when used as labels: `CAST(status AS VARCHAR)`
- Use `DOUBLE` intervals as-is; do not cast renewal intervals.

### 3.3 Subqueries vs CTEs
- Prefer CTEs (`WITH`) over nested subqueries for readability and Dremio plan optimisation.
- Name CTEs after the entity they represent: `WITH employee AS (...)`.

### 3.4 LIMIT
- Always add `LIMIT 100` (or less) in ad-hoc exploration queries.
- Never add LIMIT to VDS definitions — let the consumer control row count.

### 3.5 Validation Before VDS Creation
- Always run `validate_sql_query` before calling `create_virtual_dataset`.
- Fix all schema errors before creating the VDS — partial VDS creation cannot be undone cleanly.

---

## 4. VDS Creation Standards

### 4.1 Naming Convention
```
<source_system>_<domain>_<entity>_vds
```
Examples: `amos_training_pqs_qualification_vds`, `amos_inventory_part_status_vds`

### 4.2 Folder Structure in dremio-db
```
dremio-db/
  <amos_module>/          e.g. amos_training, amos_inventory, amos_maintenance
    <report_name>/
      <vds_name>
```

### 4.3 VDS SQL Requirements
Every VDS SQL must:
- List all columns explicitly (no SELECT *)
- Include converted dates (not raw integers)
- Include `cert_link` if the entity has document attachments
- Use DISTINCT where department/workgroup fan-out is possible
- Include a descriptive comment block at the top (for documentation)

### 4.4 VDS Comment Block Template
```sql
-- VDS  : <vds_name>
-- Jira : <ADL-ticket>
-- Src  : <source tables>
-- Desc : <one-line description>
```

---

## 5. Performance Rules

### 5.1 Avoid Expensive Operations
- No `SELECT COUNT(*)` without a WHERE clause on large AMOS tables.
- No `ORDER BY` in VDS definitions — sort at the BI/reporting layer.
- No `DISTINCT` + `ORDER BY` on large result sets without a LIMIT.

### 5.2 Reflection-Friendly Patterns
Dremio can accelerate queries with reflections when:
- Aggregations use standard functions (SUM, COUNT, AVG, MAX, MIN).
- Filter columns are simple equality conditions, not functions.
- Avoid wrapping filter columns in functions: use `expiry_date_converted >= date` not `YEAR(expiry_date_converted) = 2026`.

### 5.3 JOIN Order
- Place the largest/most-filtered table first (leftmost in FROM).
- Put small lookup/dimension tables in subsequent JOINs.

---

## 6. Catalog Column Validation (Mandatory Before Every VDS Creation)

Before finalising any SQL query, call `_validate_columns_against_catalog()` (workflow) or
manually verify every `alias.column` reference against `catalog_data.json`.

**Rule 6.0 — Always resolve column names from the catalog first:**

1. For every source table in the query, call `search_catalog('<table_name>')` to retrieve
   the exact column list from `catalog_data.json`.
2. Cross-check every `alias.column` reference in the generated SQL against the catalog result.
3. If a column is NOT in the catalog for that table, flag it as a potential error before running.
4. Common LLM column-name mistakes to auto-fix:

| LLM generates | Correct catalog name | Table |
|---|---|---|
| `pn` | `partno` | `rotables` |
| `sn` | `serialno` | `rotables` |
| `part_no` | `partno` | `rotables` |
| `serial_no` | `serialno` | `rotables` |

5. Only proceed to `validate_sql_query` (Dremio API) **after** catalog check passes or the
   user explicitly overrides a warning.

> The `_validate_columns_against_catalog(sql)` function in `workflow.py` runs this check
> automatically after every SQL generation step. Look for `⚠ CATALOG WARNINGS` output.

---

## 7. Quality Checklist (Run Before Every Query Submission)

- [ ] All AMOS date fields converted with DATE_ADD
- [ ] cert_link derived via CASE WHEN on db_link LEFT JOIN
- [ ] db_link filtered by source_type on the JOIN condition
- [ ] NULLIF applied correctly by type: `NULLIF(col, '')` for VARCHAR only — never on numeric/double/integer columns (causes "invalid input syntax" error)
- [ ] UPPER applied to workgroup before address join
- [ ] All string equality comparisons use `UPPER(col) = UPPER(literal)` on both sides
- [ ] SELECT * replaced with explicit column list
- [ ] DISTINCT added where dimension joins could fan out
- [ ] No ORDER BY in VDS definitions
- [ ] validate_sql_query passed before VDS creation
- [ ] VDS name follows naming convention
- [ ] Comment block added to VDS SQL
- [ ] All reserved keyword column names double-quoted at EVERY occurrence — value, type, status, date, time, timestamp, end, start, key, level, row, rank, position, group, order, percent, year, month, day, hour, minute, second
- [ ] AMOS source consistency: if any table is from amos_postgres, ALL tables are from amos_postgres (never mix with mm.table, SAP, Xero etc.)
- [ ] AMOS aircraft joined on `ac_registr` (not `tail_number` — that belongs to the MM aircraft table)
- [ ] `rotables` table columns use `partno` and `serialno` (not standard abbreviations like `pn`, `sn`, `part_no`, or `serial_no`)

