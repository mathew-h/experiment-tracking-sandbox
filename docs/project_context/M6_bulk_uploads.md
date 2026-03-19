# Milestone 6: Bulk Upload Feature

**Owner:** All three agents
**Branch:** `feature/m6-bulk-uploads`

**Upload types (one UI card per type):** New Experiments, Scalar Results, ICP Data (CSV), XRD Report (ActLabs), XRD Data (Aeris), pXRF Readings, Rock Inventory, Chemical Inventory, Experiment Status Update, Quick Upload.

**Per card:** Drag-and-drop file picker, pre-upload file type validation, progress indicator, response display (success count / partial error table / failure summary), template download, help text.

**After every successful upload:** calculation engine must run for all affected records.

**Atomic transactions:** a malformed file writes zero rows.

**Template files** in `docs/upload_templates/` — must match existing parser column expectations exactly.

**Test Writer Agent:** Round-trip tests per upload type, atomic transaction tests, UI validation tests.
**Documentation Agent:** `docs/user_guide/BULK_UPLOADS.md`, `docs/developer/ADDING_UPLOAD_TYPE.md`.
