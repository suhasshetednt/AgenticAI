# Spec: Update Existing VDS Flow

## Objective
Replace the primitive "paste-an-ID" menu option `[7] Update existing VDS` with a fully interactive, guided terminal workflow in `adl_automated_delivery_pipeline.py`. The new flow will allow a user to traverse the catalog, select an existing VDS, securely iterate on its SQL query using LLM-assisted edits, and apply the update after stringent validation and backup procedures.

## Core Features
1. **Interactive Catalog Traversal**
   - Provide a numbered, recursive terminal menu starting at `dremio-db`.
   - Distinguish visually between folders `[DIR]` and views `[VDS]`.
   - Restrict selection exclusively to `VIRTUAL` datasets. Attempting to select a Physical Dataset (PDS) or folder as a VDS will display an error message and maintain the prompt.
   - Support intuitive navigation options: `[U]` to go up one level, `[C]` to cancel and return to the main menu.

2. **Automated SQL Extraction & Display**
   - Automatically fetch the selected VDS's metadata and extract the SQL string.
   - Robustly handle both payload shapes: `item["sql"]` and `item["virtualDataset"]["sql"]`.
   - Print the existing SQL for user review before proceeding.

3. **Iterative LLM Edit Loop**
   - Prompt the user: `Edit this query? [y/n]`.
   - Collect natural language instructions for the desired changes.
   - Utilize the existing Dremio rules engine, system prompts, and deterministic Calcite fix-ups (`_fix_dremio_sql`, `_fix_reserved_keywords`, `_remove_semicolons`, `_strip_fences`) to generate the new SQL.
   - Display the new SQL and offer options: `[1] Accept`, `[2] Refine more`, `[3] Cancel`.
   - On acceptance, save the generated SQL locally (`_save_sql`) and display the local path.

4. **Strict Validation Gate**
   - Perform an `EXPLAIN` validation on the accepted SQL using `validate_sql_query` *before* touching the live catalog.
   - If validation fails, display the exact error and immediately loop the user back to the refinement stage.
   - Ensure the live VDS is never modified if validation fails.

5. **Safe Operational Actions (Backup / Delete / Cancel)**
   - Before applying the new SQL, prompt the user for the disposition of the old VDS:
     - **Backup:** Copy the old SQL to `<folder>/backup/<vds_name>_<timestamp>`. Only proceed to `DROP VIEW` the original if the copy is successful.
     - **Delete:** `DROP VIEW` the original VDS without backing up.
     - **Cancel:** Abort the entire operation leaving the old VDS completely intact.

6. **Recreate Phase**
   - Call `create_virtual_dataset(space, folder, vds_name, new_sql)` to recreate the VDS at its original path with the new SQL.
   - Output the new `id` and `path`.
   - Log all destructive and creative actions comprehensively to the `audit()` log.

## New Helper Functions Required
The following functions will be implemented within the workflow file to support the interactive elements:
- `_pick_existing_vds()`: Handles the interactive recursion, state, and UI for folder traversal.
- `_read_vds_sql(vds_path)`: Extractor utility to reliably obtain SQL from the API response payload.
- `_llm_rewrite_sql(existing_sql, instructions, rules)`: Core wrapper for interacting with the LLM.
- `_edit_vds_sql_loop(...)`: Higher-level orchestration of the edit/refine/accept lifecycle.

## Out of Scope
- In-place PUT updates via `update_virtual_dataset` (User requested Backup/Delete + Recreate paradigm instead).
- Multi-catalog traversal (will strictly remain within `dremio-db`).
- Modifications to the behaviors of menu options `[1]–[6]` or `[8]`.
