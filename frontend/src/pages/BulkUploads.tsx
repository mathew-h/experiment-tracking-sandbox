import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Select } from '@/components/ui'
import { bulkUploadsApi, NextIds } from '@/api/bulkUploads'
import { UploadRow } from './BulkUploadRow'

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

// ─── Page ─────────────────────────────────────────────────────────────────────
/** Bulk data upload page: one row per upload type with template download and status feedback. */
export function BulkUploadsPage() {
  const [openRow, setOpenRow] = useState<string | null>(null)
  const [elemDefaultUnit, setElemDefaultUnit] = useState('ppm')
  const [xrdMode, setXrdMode] = useState<XrdMode>('sample')

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

        {/* 1 — Master Results Sync */}
        <UploadRow
          id="master-results"
          title="Master Results Sync"
          description="Sync from SharePoint or upload the master tracking spreadsheet"
          helpText="Reads the 'Dashboard' sheet. Required columns: Experiment ID, Duration (Days). Sync reads from the configured SharePoint path; upload allows a manual override."
          accept=".xlsx,.xls"
          uploadFn={(file) => bulkUploadsApi.uploadMasterResults(file)}
          syncFn={() => bulkUploadsApi.triggerMasterSync()}
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
          uploadFn={(file) => bulkUploadsApi.uploadIcpOes(file)}
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
          uploadFn={(file) => bulkUploadsApi.uploadXrdMineralogy(file)}
          templateType="xrd-mineralogy"
          templateMode={xrdMode}
          topContent={<XrdModeToggle mode={xrdMode} onChange={setXrdMode} />}
          isOpen={isOpen('xrd-mineralogy')}
          onToggle={() => toggle('xrd-mineralogy')}
        />

        {/* 4 — Solution Chemistry */}
        <UploadRow
          id="scalar-results"
          title="Solution Chemistry"
          description="Upload solution chemistry measurements (pH, NH₄, H₂, conductivity)"
          helpText="Required columns: Experiment ID, Time (days). All other fields are optional. Set Overwrite=TRUE to replace existing values."
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadScalarResults(file)}
          templateType="scalar-results"
          isOpen={isOpen('scalar-results')}
          onToggle={() => toggle('scalar-results')}
        />

        {/* 5 — New Experiments */}
        <UploadRow
          id="new-experiments"
          title="New Experiments"
          description="Bulk-create experiments from a structured Excel template"
          helpText="Use the template for correct column formatting. The file must have an 'experiments' sheet; a 'conditions' sheet is optional."
          accept=".xlsx,.xls"
          uploadFn={(file) => bulkUploadsApi.uploadNewExperiments(file)}
          templateType="new-experiments"
          topContent={<NextIdChips data={nextIds} />}
          isOpen={isOpen('new-experiments')}
          onToggle={() => toggle('new-experiments')}
        />

        {/* 6 — Timepoint Modifications */}
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

        {/* 7 — Rock Inventory */}
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

        {/* 8 — Chemical Inventory */}
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

        {/* 9 — Sample Chemical Composition */}
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

        {/* 10 — ActLabs Rock Analysis */}
        <UploadRow
          id="actlabs-rock"
          title="ActLabs Rock Analysis"
          description="Import ActLabs titration report (Excel or CSV)"
          helpText="Accepts ActLabs standard report format. Row 3 = analyte symbols, Row 4 = units. Values like '<0.01', 'nd', 'na' are handled. Analytes are auto-created from file headers."
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadActlabsRock(file)}
          isOpen={isOpen('actlabs-rock')}
          onToggle={() => toggle('actlabs-rock')}
        />

        {/* 11 — Experiment Status Update */}
        <UploadRow
          id="experiment-status"
          title="Experiment Status Update"
          description="Bulk-set ONGOING / COMPLETED statuses"
          helpText="Required column: experiment_id. Listed experiments are set to ONGOING; other HPHT experiments currently ONGOING are set to COMPLETED. Optional: reactor_number column."
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadExperimentStatus(file)}
          templateType="experiment-status"
          isOpen={isOpen('experiment-status')}
          onToggle={() => toggle('experiment-status')}
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
    </div>
  )
}
