---
name: style-guides
description: ASL Aviation Holdings' two internal style guides — (a) Brand Guidelines (logos, colours, fonts, stationery, business cards, email signatures, ID cards, PowerPoint templates, vehicles, signage, uniforms, advertising) and (b) Finance Reporting Rules (file naming, spreadsheet design, table formatting, number/percentage/text conventions). Use whenever the user asks about ASL branding, the ASL logo or its variants (Aviation Holdings, Airlines Ireland/France/Belgium/UK/Hungary/Australia/Switzerland, Maintenance, etc.), linear vs stacked logos, brand colours (Pantone 287C/297C), the Brand Guardian, or ASL templates (incl. Project Darwin, The ASL Way). Also use for ASL financial reporting — how to format a P&L or financial table, conventions for negatives, percentages, decimals, currency, totals or zeros; file-naming (yyyy_mm_dd_…); spreadsheet design; or laying numbers on a slide. Trigger even when the user only mentions "the brand guide" or "the reporting rules", or asks for a deliverable in ASL house style.
---

# ASL Style Guides

This skill is the central reference for two ASL Aviation Holdings internal style guides:

1. **Brand Guidelines** (Version 7.0, 2023) — the rules of the ASL visual identity: logos, colours, typography, stationery, business cards, email signatures, ID cards, PowerPoint templates, vehicles, signage, promotional items, uniforms, and advertising. Owned by ASL Corporate Affairs; the **Brand Guardian** is the custodian of the brand and must approve any use not specifically covered.
2. **Finance Reporting Rules** (26 April 2022) — the rules for presenting financial and management analysis: file naming, spreadsheet design, table formatting, and conventions for numbers, percentages, and text.

Both guides apply across ASL Aviation Holdings and all ASL airlines and companies (ASL Airlines Ireland, France, Belgium, United Kingdom, Hungary, Australia; ASL Airline Services Switzerland; ASL Maintenance; and group functions such as Corporate Affairs, HR, IT, etc.).

## How to use this skill

- **For any brand-identity question** — logos, colours, fonts, stationery, templates, livery, signage, uniforms, or advertising — read [`references/branding.md`](references/branding.md).
- **For any financial-reporting question** — file naming, spreadsheet design, table or slide formatting of financial data, number/percentage conventions — read [`references/finance-reporting.md`](references/finance-reporting.md).
- **For the source documents themselves** — the original PDF and PPTX live in `assets/` (`2023_10_31_Branding_Guide.pdf` and `ASL_Finance_Reporting_Rules.pptx`). Open them when an exact visual reference is needed (e.g. to see the actual letterhead layout or the worked P&L example).

## Quick reference card

**Brand colours**

| Colour | Pantone | CMYK | RGB | HEX |
|---|---|---|---|---|
| ASL Dark Blue | 287C | 100 / 68 / 0 / 12 | 0 / 75 / 147 | `#004B93` |
| ASL Light Blue | 297C | 49 / 1 / 0 / 0 | 134 / 208 / 244 | `#86D0F4` |
| ASL Grey | 287C* | 44 / 33 / 32 / 11 | 147 / 149 / 153 | `#939599` |

*Note: ASL Grey is shown with Pantone 287C in the source — likely a typo; verify with Brand Guardian before reproducing in print.

**Standard font:** Calibri 11pt for all letters, emails, presentations, and written/digital communications. Logos themselves use stylised Gotham Black Italic ("ASL") and Gotham Bold Italic (suffix). Any other font requires Brand Guardian approval.

**Logo minimum size for print:** 30mm width. Safe area: ≥10mm around the basic grid.

**Linear logos:** exceptional use only (e.g. airport ID badges, height-restricted vehicle panels). Never on email signatures, stationery, PowerPoint, or call-service backgrounds.

**File naming (finance reports):** `yyyy_mm_dd_name of report_company` (e.g. `2024_06_30_Management_Accounts_ASLF`).

**Negative numbers:** always in `(brackets)`, never red.
**Negative percentages:** with a `-` sign, not brackets.
**Number format string:** `#,##0;(#,##0);"-"`.

## Conventions used in this skill

- "ASL" without a suffix refers to the group as a whole (ASL Aviation Holdings DAC).
- "ASL Airlines" with a country suffix refers to a specific operating airline (e.g. ASL Airlines Ireland, ASL Airlines France).
- "Brand Guardian" refers to the designated brand custodian, contacted via ASL Group Corporate Affairs.
- Where a rule is described as **"unless approved by the Brand Guardian"**, it is a hard rule for all routine use; exceptions exist but require advance written approval.

## When applying these guides

When Claude is asked to produce a deliverable — a slide deck, a Word doc, an email, a financial report, a chart — for ASL or one of its airlines/companies, apply both guides in combination:
- **Visuals** (colours, fonts, logo, layout) follow the Brand Guidelines.
- **Numbers** (tables, P&Ls, KPIs, comparisons) follow the Finance Reporting Rules.

If the user has not specified which airline or company a deliverable is for, ask — the correct logo variant and stationery template depend on it. Default to the ASL Aviation Holdings logo and PowerPoint template for group-level or department deliverables (HR, IT, Finance, etc.).

When in doubt, the guides are the source of truth. If something is genuinely not covered, flag it and note that Brand Guardian approval would be needed.
