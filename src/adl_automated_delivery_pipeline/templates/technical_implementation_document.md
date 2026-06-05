# {{title}}

{{subtitle}}

Prepared: {{metadata.prepared}}  |  {{metadata.team}}

## 1. Project
<!-- one line: the project this work belongs to (ASL Airlines — ADL DataLake Integration) -->

## 2. Team
<!-- the delivery team name -->

## 3. Stakeholders
<!-- bullet list of stakeholders with role and organisation -->

## 4. Initial Requirements
<!-- a 2-3 sentence narrative of the business context, then a bullet list of what each VDS/output delivers, grounded in data.business_requirement -->

## 5. Additional Requirements
<!-- bullet list of edge cases, null/exclusion handling, data-quality and scope constraints from data.transformations and data.filter_conditions -->

## 6. Risks & Mitigation
<!-- a table of 3-5 technical/data/performance risks and their mitigations -->

| Risk | Mitigation |
|------|------------|

## 7. Process Continuity
<!-- a table: what happens if a source is missing or the VDS is unavailable, and the fallback -->

| Issue | Mitigation |
|-------|------------|

## 8. Implementation

### 8.1 Data Sources
<!-- a table of source tables from data.source_tables: name, full path, description -->

| Table Name | Full Path | Description |
|------------|-----------|-------------|

### 8.2 Interface Process
<!-- for each VDS/component, a short heading then bullet steps describing select, joins, filters, output naming, grounded in data.transformations and data.filter_conditions -->

## 9. Data Dictionary
<!-- one table row per output field in data.output_fields: Dremio field, source field, derivation logic -->

| Dremio Field | Source Field | Logic / Derivation |
|--------------|--------------|--------------------|

## 10. Milestones
<!-- a table of delivery milestones with day estimates summing to 9-14 working days -->

| Milestone | Days |
|-----------|------|

## 11. Reference

### 11.1 VDS Output Path
<!-- state the VDS output path from data.vds_path, or a reasonable default under dremio-db -->

### 11.2 Key Business Rules
<!-- bullet list of the key business rules: date/status filters, null handling, deduplication/grouping -->

### 11.3 Access Control
<!-- one sentence: who has SELECT vs write access to the VDS output -->

## 12. Sign-off
<!-- a table with columns Role, Name, Date and rows for Technical Lead, Development Lead, QA/Tester, Business Owner (leave Date blank) -->

| Role | Name | Date |
|------|------|------|
