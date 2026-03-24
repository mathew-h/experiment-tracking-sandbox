# Sample Management — User Guide

This guide covers the **Samples** section of the lab app: creating geological samples, uploading photos, adding analyses, and understanding the **Characterized** status.

---

## What Is a Sample?

A **Sample** (`SampleInfo`) is a geological rock specimen that can be linked to one or more experiments. Each sample has a unique string ID (e.g., `SMP-042`), optional geographic metadata (country, locality, lat/lon), and a **Characterized** flag that summarises whether the sample has been analytically characterised.

---

## Navigating to Samples

Click **Samples** in the left navigation bar. The inventory table shows all samples with search and filter controls at the top.

### Filters

| Filter | Description |
|--------|-------------|
| Search | Matches sample ID or locality (case-insensitive) |
| Country | Exact country match |
| Characterized | Show only characterized / uncharacterized samples |
| pXRF / XRD / Elemental | Show only samples that have the selected analysis type |

---

## Creating a New Sample

1. Click **+ New Sample** (top-right of the inventory page).
2. Fill in the **Sample Details** on the left:
   - **Sample ID** (required) — unique string identifier, e.g. `SMP-101`
   - Rock classification, country, state, locality, description
   - Latitude / longitude (decimal degrees) — enables the map view when coordinates are provided
3. Optionally add the first **Analysis** on the right panel (pXRF, XRD, Elemental, etc.).
4. Optionally upload the first **Photo**.
5. Click **Create Sample**.

The `characterized` status is evaluated automatically on creation based on the analyses provided.

---

## Sample Detail Page

Click any row in the inventory to open the **Sample Detail** page. It has four tabs:

### Overview tab

Shows all metadata fields in read/edit mode. Click **Edit** to update any mutable field. Linked experiments are listed at the bottom (read-only).

### Photos tab

Upload, view, and delete photos associated with the sample.

- Accepted formats: JPEG, PNG
- Maximum file size: 20 MB per photo
- Photos are stored on the lab server and displayed in a grid gallery

### Analyses tab

Lists all **ExternalAnalysis** records attached to this sample, grouped by type (pXRF, XRD, SEM, Elemental, Titration, etc.).

**Adding an analysis:**
1. Select the analysis type from the dropdown
2. Fill in date, laboratory, analyst, and any type-specific fields:
   - **pXRF**: enter the reading number from the pXRF instrument log
   - **Magnetic susceptibility**: enter the measured value
3. Click **Add Analysis**

**pXRF reading numbers:** The app normalises reading numbers automatically (strips whitespace, converts `"1.0"` to `"1"`) and checks them against the imported pXRF database. If a reading is not found you will see a yellow warning — the analysis is still saved, but the reading is not linked to raw elemental data.

**Deleting an analysis:** Click the trash icon on any analysis card. The `characterized` status is re-evaluated automatically.

### Activity tab

A chronological log of all create/update/delete operations on this sample, pulled from the audit trail.

---

## Characterized Status

The **Characterized** badge (green = Characterized, grey = Uncharacterized) reflects whether the sample meets the analytical characterisation criteria. It is evaluated automatically whenever analyses are added or removed.

A sample is considered **Characterized** if it satisfies **at least one** of the following:

| Criterion | Requires |
|-----------|----------|
| Mineralogy | An XRD `ExternalAnalysis` **and** a linked `XRDAnalysis` record (mineral phases data) |
| Bulk chemistry | An Elemental or Titration `ExternalAnalysis` **and** at least one `ElementalAnalysis` row |
| Portable XRF | A pXRF `ExternalAnalysis` **and** a matching `PXRFReading` in the database |

You can also manually override the `characterized` field from the Overview tab — a manual set takes precedence over the automatic evaluation for that update only; subsequent analysis changes will re-evaluate it automatically.

---

## Map View (Upcoming)

Samples with latitude/longitude coordinates will be shown on a map. This feature is currently bookmarked and will be added in a future milestone. In the meantime, all samples with coordinates are available via the `/api/samples/geo` endpoint for external tools.

---

## Tips

- Use the **SampleSelector** in the New Experiment wizard to search for samples by ID or locality without typing the full ID.
- The **Characterized** filter is useful for quickly finding samples that are ready to be used in a new experiment.
- The Activity tab provides a full audit trail if you need to trace when and who changed a sample record.
