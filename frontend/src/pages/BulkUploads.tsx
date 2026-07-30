import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Select } from '@/components/ui'
import { bulkUploadsApi, NextIds } from '@/api/bulkUploads'
import { UploadRow, IconChevron } from './BulkUploadRow'
import { ActlabsUploadRow } from './ActlabsUploadRow'
import { NewExperimentsUploadRow } from './NewExperimentsUploadRow'

// ─── Next-ID chips (New Experiments card) ────────────────────────────────────
function NextIdChips({ data }: { data: NextIds | undefined }) {
  if (!data) return null
  const fmt = (n: number) => String(n).padStart(3, '0')
  return (
    <div className="flex flex-wrap gap-2 py-1">
      <span className="text-xs text-ink-muted">Next IDs:</span>
      {(['HPHT', 'Serum', 'CF', 'Autoclave'] as const).map((type) => (
        <span
          key={type}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-raised border border-surface-border text-xs"
        >
          <span className="text-ink-muted">{type}:</span>
          <span className="font-mono-data text-ink-primary">{fmt(data[type])}</span>
        </span>
      ))}
    </div>
  )
}

// ─── Default-unit selector (Elemental Composition card) ──────────────────────
const UNIT_OPTIONS = [
  { value: 'ppm', label: 'ppm' },
  { value: '%', label: '%' },
  { value: 'wt%', label: 'wt%' },
  { value: 'mM', label: 'mM' },
  { value: 'ppb', label: 'ppb' },
]

function DefaultUnitField({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-ink-muted shrink-0">Default unit for new analytes:</span>
      <Select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        options={UNIT_OPTIONS}
        className="w-28"
      />
    </div>
  )
}

// ─── XRD mode toggle ─────────────────────────────────────────────────────────
type XrdMode = 'sample' | 'experiment'

function XrdModeToggle({ mode, onChange }: { mode: XrdMode; onChange: (m: XrdMode) => void }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-ink-muted shrink-0">Template format:</span>
      <div className="flex rounded border border-surface-border overflow-hidden text-xs">
        <button
          className={`px-2.5 py-1 transition-colors ${
            mode === 'sample'
              ? 'bg-surface-raised text-ink-primary font-medium'
              : 'text-ink-muted hover:text-ink-secondary hover:bg-surface-secondary'
          }`}
          onClick={() => onChange('sample')}
        >
          Sample-based
        </button>
        <button
          className={`px-2.5 py-1 border-l border-surface-border transition-colors ${
            mode === 'experiment'
              ? 'bg-surface-raised text-ink-primary font-medium'
              : 'text-ink-muted hover:text-ink-secondary hover:bg-surface-secondary'
          }`}
          onClick={() => onChange('experiment')}
        >
          Experiment + Timepoint
        </button>
      </div>
    </div>
  )
}

// ─── XRD overwrite toggle ─────────────────────────────────────────────────────
function XrdOverwriteToggle({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          className="w-3.5 h-3.5 rounded accent-red-500"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="text-xs text-ink-secondary">
          Replace existing results for matching experiment / timepoint
        </span>
      </label>
      {checked ? (
        <p className="text-xs text-amber-400 leading-relaxed pl-5">
          All existing mineral phases for any matching experiment and timepoint in this file
          will be deleted and replaced with the values from this upload.
        </p>
      ) : (
        <p className="text-xs text-ink-muted leading-relaxed pl-5">
          Existing mineral phases for the same experiment and timepoint will be left
          unchanged. Only new phases will be added.
        </p>
      )}
    </div>
  )
}

// ─── ICP overwrite toggle ─────────────────────────────────────────────────────
function IcpOverwriteToggle({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          className="w-3.5 h-3.5 rounded accent-red-500"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="text-xs text-ink-secondary">
          Replace existing ICP data instead of merging
        </span>
      </label>
      {checked ? (
        <p className="text-xs text-amber-400 leading-relaxed pl-5">
          Existing ICP elemental data for matching experiments and timepoints will be
          deleted and replaced with only the values from this upload.
        </p>
      ) : (
        <p className="text-xs text-ink-muted leading-relaxed pl-5">
          Default: new elements are added and conflicting values are overwritten, but
          elements absent from this file are preserved.
        </p>
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────
/** Bulk data upload page: one row per upload type with template download and status feedback. */
export function BulkUploadsPage() {
  const [openRow, setOpenRow] = useState<string | null>(null)
  const [elemDefaultUnit, setElemDefaultUnit] = useState('ppm')
  const [xrdMode, setXrdMode] = useState<XrdMode>('sample')
  const [xrdOverwrite, setXrdOverwrite] = useState(false)
  const [icpOverwrite, setIcpOverwrite] = useState(false)
  const [showInactive, setShowInactive] = useState(false)

  const toggle = (id: string) => setOpenRow((prev) => (prev === id ? null : id))
  const isOpen = (id: string) => openRow === id

  // Next-IDs query — staleTime 60s, only used in "new-experiments" row
  const { data: nextIds } = useQuery({
    queryKey: ['nextIds'],
    queryFn: bulkUploadsApi.getNextIds,
    staleTime: 60_000,
  })

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold text-ink-primary">Bulk Uploads</h1>
        <p className="text-xs text-ink-muted mt-0.5">
          Upload analytical data from instrument exports and spreadsheets
        </p>
      </div>

      <div className="space-y-2">

        {/* ── Active uploads — most-used, full prominence ─────────────────── */}

        {/* 1 — Master Results Sync (drag-and-drop; the broken SharePoint sync was removed, issue #74) */}
        <UploadRow
          id="master-results"
          title="Master Results Sync"
          description="Drag and drop the master tracker spreadsheet to push updates"
          helpText={
            'Drag and drop the master results file into the zone below to push updates: ' +
            '01_R&D\\02_Results\\Master_Reactor_Sampling_Tracker_v2.xlsx — ' +
            "reads the 'Dashboard' sheet. Required columns: Experiment ID, Duration (Days). " +
            'Replicates: either write the full lettered ID (SERUM_001a) in Experiment ID, or put the base ID there and the letter (a, b, c) in the optional Replicate column — 0 or blank means the group parent. ' +
            'If the Experiment ID carries -t<days>, a blank Duration (Days) is filled from the ID; a different Duration errors the row.'
          }
          accept=".xlsx,.xls"
          uploadFn={(file) => bulkUploadsApi.uploadMasterResults(file)}
          prominent
          isOpen={isOpen('master-results')}
          onToggle={() => toggle('master-results')}
        />

        {/* 2 — ICP-OES Data */}
        <UploadRow
          id="icp-oes"
          title="ICP-OES Data"
          description="Upload ICP-OES elemental analysis CSV"
          helpText="Instrument CSV export from the ICP-OES. Multi-element, multi-timepoint files supported. Blank rows are filtered. Duplicate spectral lines resolved by best intensity."
          accept=".csv"
          uploadFn={(file) => bulkUploadsApi.uploadIcpOes(file, icpOverwrite)}
          topContent={<IcpOverwriteToggle checked={icpOverwrite} onChange={setIcpOverwrite} />}
          prominent
          isOpen={isOpen('icp-oes')}
          onToggle={() => toggle('icp-oes')}
        />

        {/* 3 — XRD Mineralogy */}
        <UploadRow
          id="xrd-mineralogy"
          title="XRD Mineralogy"
          description="Upload XRD mineral phase data — auto-detects format from column names"
          helpText={
            xrdMode === 'experiment'
              ? "Experiment+Timepoint format: include 'Experiment ID' and 'Time (days)' columns plus one column per mineral phase. The format is auto-detected on upload."
              : "Sample-based format: include a 'sample_id' column plus one column per mineral phase. Aeris instrument exports (sample IDs like '20260218_HPHT070-d19_02') are also accepted."
          }
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadXrdMineralogy(file, xrdOverwrite)}
          templateType="xrd-mineralogy"
          templateMode={xrdMode}
          topContent={
            <>
              <XrdModeToggle mode={xrdMode} onChange={setXrdMode} />
              <XrdOverwriteToggle checked={xrdOverwrite} onChange={setXrdOverwrite} />
            </>
          }
          skippedMessage={
            !xrdOverwrite
              ? "Some rows were skipped because data already exists for these timepoints. Enable 'Replace existing results' to overwrite."
              : undefined
          }
          prominent
          isOpen={isOpen('xrd-mineralogy')}
          onToggle={() => toggle('xrd-mineralogy')}
        />

        {/* 4 — New Experiments — preview-first (issue #100 items 6-9) */}
        <NewExperimentsUploadRow
          topContent={<NextIdChips data={nextIds} />}
          prominent
          isOpen={isOpen('new-experiments')}
          onToggle={() => toggle('new-experiments')}
        />

        {/* 5 — Experiment Status Update */}
        <UploadRow
          id="experiment-status"
          title="Experiment Status Update"
          description="Bulk-set experiment status (ONGOING / COMPLETED / QUEUED / CANCELLED)"
          helpText="Required columns: experiment_id, status. Optional: reactor_number, date (start date). Setting an HPHT or Core Flood experiment to ONGOING with a reactor_number auto-completes an older experiment in the same reactor; a newer-or-equal-dated occupant triggers a warning instead of a completion."
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadExperimentStatus(file)}
          templateType="experiment-status"
          prominent
          isOpen={isOpen('experiment-status')}
          onToggle={() => toggle('experiment-status')}
        />

        {/* 6 — ActLabs Rock Analysis */}
        <ActlabsUploadRow
          prominent
          isOpen={isOpen('actlabs-rock')}
          onToggle={() => toggle('actlabs-rock')}
        />

        {/* ── Less-used uploads — collapsed by default ────────────────────── */}
        <div className="pt-4">
          <button
            className="w-full flex items-center justify-between px-4 py-2.5 rounded-lg border border-surface-border bg-surface-primary hover:bg-surface-secondary transition-colors text-left"
            onClick={() => setShowInactive((v) => !v)}
            aria-expanded={showInactive}
          >
            <span className="text-xs font-medium text-ink-secondary">Less-used uploads</span>
            <IconChevron open={showInactive} />
          </button>

          {showInactive && (
            <div className="mt-2 space-y-2">

              {/* 7 — Solution Chemistry */}
              <UploadRow
                id="scalar-results"
                title="Solution Chemistry"
                description="Upload solution chemistry measurements (pH, NH₄, H₂, conductivity)"
                helpText="Required columns: Experiment ID, Time (days). All other fields are optional. Set Overwrite=TRUE to replace existing values. Replicates: either write the full lettered ID (SERUM_001a) in Experiment ID, or put the base ID there and the letter (a, b, c) in the optional Replicate column — 0 or blank means the group parent. If the Experiment ID carries -t<days>, a blank Time (days) is filled from the ID; a different Time errors the row."
                accept=".xlsx,.xls,.csv"
                uploadFn={(file) => bulkUploadsApi.uploadScalarResults(file)}
                templateType="scalar-results"
                isOpen={isOpen('scalar-results')}
                onToggle={() => toggle('scalar-results')}
              />

              {/* 8 — Timepoint Modifications */}
              <UploadRow
                id="timepoint-modifications"
                title="Timepoint Modifications"
                description="Bulk-set modification descriptions on existing result rows"
                helpText="Required columns: experiment_id, time_point, modification_description. Set overwrite_existing=TRUE to replace existing descriptions. Time is matched with ±0.0001 day tolerance."
                accept=".xlsx,.xls,.csv"
                uploadFn={(file) => bulkUploadsApi.uploadTimepointModifications(file)}
                templateType="timepoint-modifications"
                isOpen={isOpen('timepoint-modifications')}
                onToggle={() => toggle('timepoint-modifications')}
              />

              {/* 9 — Rock Inventory */}
              <UploadRow
                id="rock-inventory"
                title="Rock Inventory"
                description="Upload or update rock sample metadata"
                helpText="Required column: sample_id. Optional: rock_classification, state, country, locality, latitude, longitude, description, characterized."
                accept=".xlsx,.xls,.csv"
                uploadFn={(file) => bulkUploadsApi.uploadRockInventory(file)}
                templateType="rock-inventory"
                isOpen={isOpen('rock-inventory')}
                onToggle={() => toggle('rock-inventory')}
              />

              {/* 10 — Chemical Inventory */}
              <UploadRow
                id="chemical-inventory"
                title="Chemical Inventory"
                description="Upload or update chemical reagent records"
                helpText="Required column: name. Optional: formula, cas_number, molecular_weight, density, hazard_class, supplier, catalog_number, notes."
                accept=".xlsx,.xls,.csv"
                uploadFn={(file) => bulkUploadsApi.uploadChemicalInventory(file)}
                templateType="chemical-inventory"
                isOpen={isOpen('chemical-inventory')}
                onToggle={() => toggle('chemical-inventory')}
              />

              {/* 11 — Sample Chemical Composition */}
              <UploadRow
                id="elemental-composition"
                title="Sample Chemical Composition"
                description="Wide-format Excel with sample_id + analyte columns"
                helpText="First column must be sample_id. Remaining columns are analyte symbols (e.g. SiO2, Al2O3). Cells contain numeric values. Unknown analytes are auto-created with the selected default unit."
                accept=".xlsx,.xls"
                uploadFn={(file) => bulkUploadsApi.uploadElementalComposition(file, elemDefaultUnit)}
                templateType="elemental-composition"
                topContent={
                  <DefaultUnitField value={elemDefaultUnit} onChange={setElemDefaultUnit} />
                }
                isOpen={isOpen('elemental-composition')}
                onToggle={() => toggle('elemental-composition')}
              />

              {/* 12 — pXRF Readings */}
              <UploadRow
                id="pxrf"
                title="pXRF Readings"
                description="Upload portable XRF scan data"
                helpText="Instrument CSV or Excel export from the portable XRF. Each row is one scan. Instrument format — no template needed."
                accept=".csv,.xlsx,.xls"
                uploadFn={(file) => bulkUploadsApi.uploadPXRF(file)}
                isOpen={isOpen('pxrf')}
                onToggle={() => toggle('pxrf')}
              />

            </div>
          )}
        </div>

      </div>
    </div>
  )
}
