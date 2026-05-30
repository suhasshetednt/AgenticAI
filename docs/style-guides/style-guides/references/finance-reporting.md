# ASL Finance Reporting Rules

Source: `assets/ASL_Finance_Reporting_Rules.pptx` (ASL Aviation Group, 26 April 2022).

## Objective

> A key objective of Reporting is to provide **timely, accurate and understandable** information that leads to better decisions.

This guide describes the acceptable format for presenting analysis to make it as **understandable** as possible.

## Table of contents

1. [File and workbook management](#1-file-and-workbook-management)
2. [Spreadsheet design](#2-spreadsheet-design)
3. [General formatting principles](#3-general-formatting-principles)
4. [Table structure](#4-table-structure)
5. [Numbers](#5-numbers)
6. [Percentages](#6-percentages)
7. [Text](#7-text)
8. [Negative numbers and zeros](#8-negative-numbers-and-zeros)
9. [Worked example: standard table](#9-worked-example-standard-table)
10. [Worked example: P&L](#10-worked-example-pl)

---

## 1. File and workbook management

- **File naming convention:** `yyyy_mm_dd_name of report_company` (where applicable).
  - Example: `2024_06_30_Management_Accounts_ASLF.xlsx`.
- **No multiple versions in the working folder** — superseded files should be **clearly labelled** and moved to an **"Archive" folder**.
- **Use consistent formats** to avoid confusion across reports.
- **Tie out the numbers**: ensure numbers in your report **tie into any other related reports** (or versions). Any differences must be **reconciled and disclosed**.
- **Document your work clearly** — so you can re-familiarise yourself with the file later, or so someone else can pick it up.

---

## 2. Spreadsheet design

Design intelligent, intelligible formulas:

- **Avoid constants.** Any piece of raw data should appear in a clearly highlighted **"Input" section** of the spreadsheet.
- **Avoid hidden cells.** Instead, put the information in a different part of the worksheet (and use the **Group** feature if you need to collapse it).
- **Minimise references** to cells outside the current worksheet.
- **Add "checks"** to the workbook to ensure all tables tie into each other.

---

## 3. General formatting principles

### Formatting approaches (mindset)

- **Don't overuse visual effects** — only use them when they clarify, distinguish, or add meaning.
- **Never present numbers without context** — i.e. always show **prior-period comparisons**. Ensure comparables are lined up.
- **Never present a slide where the font is too small to read the numbers.** It takes hard work, clear thought, and discipline to select the precise information that should appear in a limited space and omit the rest.
- The audience is entitled to presume **every number in a report is meaningful**. Any data omitted should be explained to the audience.
- **Put the important numbers where they're easy to find** — usually around the edges.
- **Place appropriate emphasis on critical information.**
- Ensure the audience can determine the **unit of measure** for every number. **Omit the currency symbol from the body** of the report and include it in the **column heading** instead (e.g. `€'000`).
- **Use graphs** to identify trends and patterns and to drive home a single, fundamentally important point.

### Formatting rules (mechanics)

- **Columns of numbers are always right-justified** — never centre-aligned. This helps the audience visually identify significant numbers with ease.
- **Negative numbers in brackets**, not in red.

---

## 4. Table structure

A standard ASL financial table has these elements:

| Element | Purpose |
|---|---|
| **Table title** | Name of the table (e.g. "Profit and Loss") |
| **Spacer row** | 2pt-high blank row beneath the title |
| **Table header** | Column labels (period names, etc.); currency / denomination shown in the description column header |
| **Description column** | Left-aligned row labels (line items) |
| **Data columns** | Right-aligned numerical columns |
| **Subtotal column** | A bold-emphasised intermediate total column |
| **Total column** | The main total column (bold) |
| **Subtotal rows** | E.g. "Gross Profit"; white text on a coloured bar |
| **Total rows** | E.g. "Net Profit"; white text on a darker coloured bar |
| **Spacer row** | Separator before supplementary data |
| **Supplementary data** | Below the table — KPIs like Head Count, ACV, etc., separated by a thin black line |
| **Backup data** | Lower-level breakdowns; presented in **italics** and **grouped** in the spreadsheet; **not to be brought into PowerPoint** |

### Specifications

**Table title and spacer row**

- Font: **Calibri 10pt, Bold, Black**
- Alignment: **Merged and Left**
- Spacer row height: **2pts**

**Table header**

- Font: **Calibri 9pt, Bold, White**
- Alignment: **Left and bottom** for the description column; **Centre and bottom** for all other columns.
- Borders: **Thin white line**, except when separating high-level product types.
- The **currency and denomination** of figures appears in the description column header (e.g. `€'000`).

**Columns (data)**

- Font: **Calibri 9pt**; **bold only for the main total column**.
- Alignment: **Right**.

**Rows**

- Font: **Calibri 9pt**; **bold for all total rows**.
- Font colour: **Black**, except in Additional Subtotal rows and Total rows, where it is **White** (on a coloured fill).
- Alignment: **Right**.
- Row height: **17**.
- **Backup data**: presented in **italics** and **grouped** in the workbook; **never brought into PowerPoint**.

**Supplementary data**

- Separated from the main table by a **spacer line** and a **thin black line**.

---

## 5. Numbers

- **Font:** Calibri 9pt, Black.
- **Alignment:** Right.
- **Zero formatting:** display a dash — `-` — not `0`.
- **Negative numbers:** in `(brackets)`, **not in red**.
- **Decimal places:**
  - If **all numbers in a table are > 100**, use **no decimal place**.
  - Otherwise, **one decimal place** may be used.
  - **Never mix** numbers in a single table with and without decimals.
  - **If in doubt, do not use a decimal.**
- **Excel format string:** `#,##0;(#,##0);"-"`

---

## 6. Percentages

- **Font:** Calibri 9pt, **Italics**, Black.
- **Decimal places:** **1 decimal point** (e.g. `33.3%`).
- **Alignment:** Right.
- **Negative percentages:** shown with a `-` sign (e.g. `-50.0%`), **not in brackets**. This is the **opposite convention** to negative numbers.

---

## 7. Text

- **Font:** Calibri 9pt.
- **Alignment:** **Left and bottom-aligned**.
- **Notes beneath the table:** font size **7**.

Example of a note: `Note: XYZ calculated from ABC`.

---

## 8. Negative numbers and zeros

A single table to keep this clear, because the conventions differ:

| Value | Format |
|---|---|
| Positive number | `1,000` |
| Negative number | `(1,000)` (brackets, black, never red) |
| Zero | `-` (a single dash) |
| Positive percentage | `33.3%` (italic, 1 dp) |
| Negative percentage | `-50.0%` (italic, 1 dp, minus sign, **never brackets**) |

The reason for the asymmetry: brackets give the eye a strong visual cue for negative monetary values, but reading a column of bracketed percentages becomes cluttered, so the minus sign is preferred for percentages.

---

## 9. Worked example: Standard table

This is the canonical small-table example from the source:

|  | 2013 | 2014 | % YoY |
|---|---:|---:|---:|
| **€'000** | | | |
| Company A | 20,000 | 30,000 | *33.3%* |
| Company B | 30,000 | 20,000 | *-50.0%* |
| Company C | (10,000) | 15,000 | *166.7%* |
| Company D | 10,000 | 5,000 | *-100.0%* |
| **Total** | **50,000** | **70,000** | ***28.6%*** |

Points to note:
- Currency denomination (`€'000`) sits in the description column header.
- All number columns right-aligned, total row bold.
- Negative numbers in brackets — `(10,000)`.
- Negative percentages with a minus sign — `-50.0%`.
- Percentages in italic.
- One decimal place throughout (because not all numbers are >100 in the percentage column).

---

## 10. Worked example: P&L

This is the canonical P&L example from the source:

**Profit and Loss**

| €'000 | H1 | H2 | 2014 | Total |
|---|---:|---:|---:|---:|
| ABC | 1,000 | 4,000 | 5,000 | 10,000 |
| &nbsp;&nbsp;XX | 500 | 2,000 | 2,500 | - |
| &nbsp;&nbsp;YY | 500 | 2,000 | 2,500 | - |
| DEF | 2,000 | 3,000 | 5,000 | 10,000 |
| GHI | 3,000 | 2,000 | 5,000 | 10,000 |
| JKL | 4,000 | 1,000 | 5,000 | 10,000 |
| **Gross Profit** | **10,000** | **10,000** | **20,000** | **40,000** |
| Tax | (2,000) | (2,000) | (4,000) | (8,000) |
| **Net Profit** | **8,000** | **8,000** | **16,000** | **32,000** |

*Supplementary data (below a thin black separator):*
- Head Count: 100
- ACV: 10,000

Points to note:
- `XX` and `YY` are **backup data** rows underneath ABC, indented and presented in italics in the workbook (and grouped). They would **not** be brought into PowerPoint.
- Zeros in the Total column for backup rows display as `-`, not `0`.
- The "Total" column is the main total (bold).
- `2014` is a subtotal column (bold but in a different way to the main total).
- `Gross Profit` is a subtotal row (white text on coloured fill).
- `Net Profit` is a total row (white text on darker coloured fill).
- Tax line carries bracketed negatives.
- Supplementary KPIs (Head Count, ACV) sit below, separated by a thin black line.

---

## Quick checklist when producing a financial report or slide

Run through this before sending:

- [ ] Filename follows `yyyy_mm_dd_name_company` convention
- [ ] Old versions archived, not left in the working folder
- [ ] Numbers tie to other related reports — differences disclosed
- [ ] Inputs in a clearly marked Input section; no hidden cells
- [ ] Workbook has checks that all tables tie out
- [ ] Currency / denomination in the column heading (`€'000`), not in the body
- [ ] All number columns right-aligned
- [ ] Negative numbers in brackets, black — never red
- [ ] Zeros shown as `-`
- [ ] Percentages in italic, 1 dp, negative with `-` sign
- [ ] Decimal usage consistent across the whole table (all or none)
- [ ] Comparables (prior period / prior year) shown and lined up
- [ ] Backup data grouped, italicised, kept out of PowerPoint
- [ ] Total and subtotal rows bold, with the agreed white-on-colour fills
- [ ] Notes beneath the table at font size 7
- [ ] Font is Calibri throughout (9pt body, 10pt title, 7pt notes)
- [ ] No visual effects unless they add meaning
- [ ] Font is readable — if numbers are too small to read on the slide, cut content rather than shrink type
