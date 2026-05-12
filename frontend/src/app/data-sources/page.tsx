'use client'

import { type ReactNode, useEffect, useMemo, useState } from 'react'

import { api } from '@/services/api'
import {
  DataSourceCapability,
  DataSourceBootstrapAssetSummary,
  DataSourceBootstrapRunResult,
  DataSourceDashboardData,
  DataSourceMissingDataAction,
  DataSourceProviderStatus,
  FreeDerivativesArtifact,
  FreeDerivativesBootstrapRun,
  FreeDerivativesBootstrapRunSummary,
  FreeDerivativesSourceResult,
  FirstEvidenceRunResult,
} from '@/types'

const OPTIONAL_PROVIDER_TYPES = new Set([
  'kaiko_optional',
  'tardis_optional',
  'coinglass_optional',
  'cryptoquant_optional',
  'cme_quikstrike_local_or_optional',
])

const FREE_DERIVATIVES_PROVIDER_TYPES = new Set([
  'cftc_cot',
  'gvz',
  'deribit_public_options',
])

export default function DataSourcesPage() {
  const [data, setData] = useState<DataSourceDashboardData | null>(null)
  const [firstRun, setFirstRun] = useState<FirstEvidenceRunResult | null>(null)
  const [bootstrapRun, setBootstrapRun] = useState<DataSourceBootstrapRunResult | null>(null)
  const [freeDerivativesRun, setFreeDerivativesRun] =
    useState<FreeDerivativesBootstrapRun | null>(null)
  const [firstRunId, setFirstRunId] = useState('')
  const [bootstrapRunId, setBootstrapRunId] = useState('')
  const [freeDerivativesRunId, setFreeDerivativesRunId] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingRun, setLoadingRun] = useState(false)
  const [loadingBootstrap, setLoadingBootstrap] = useState(false)
  const [loadingFreeDerivatives, setLoadingFreeDerivatives] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)
  const [freeDerivativesError, setFreeDerivativesError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    api.getDataSourceDashboardData()
      .then((response) => {
        if (!active) return
        setData(response)
        const latestBootstrap = response.bootstrapRuns.runs[0] ?? null
        setBootstrapRun(latestBootstrap)
        setBootstrapRunId(latestBootstrap?.bootstrap_run_id ?? '')
        setFreeDerivativesRun(response.latestFreeDerivativesRun)
        setFreeDerivativesRunId(response.latestFreeDerivativesRun?.run_id ?? '')
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Data-source readiness could not be loaded')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  const providerStatuses = data?.readiness.provider_statuses ?? []
  const capabilityRows = data?.capabilities.capabilities ?? data?.readiness.capability_matrix ?? []
  const freeDerivativeStatuses = providerStatuses.filter((status) =>
    FREE_DERIVATIVES_PROVIDER_TYPES.has(status.provider_type),
  )
  const freeDerivativeCapabilities = capabilityRows.filter((row) =>
    FREE_DERIVATIVES_PROVIDER_TYPES.has(row.provider_type),
  )
  const optionalStatuses = providerStatuses.filter((status) =>
    OPTIONAL_PROVIDER_TYPES.has(status.provider_type),
  )
  const defaultMissingActions = data?.missingData.actions ?? []
  const readinessMissingActions = data?.readiness.missing_data_actions ?? []
  const bootstrapRuns = data?.bootstrapRuns.runs ?? []
  const freeDerivativeRuns = data?.freeDerivativesRuns.runs ?? []
  const missingActions = useMemo(
    () => dedupeActions([...readinessMissingActions, ...defaultMissingActions]),
    [readinessMissingActions, defaultMissingActions],
  )
  const xauAction = missingActions.find((action) => action.workflow_type === 'xau_vol_oi')
  const freeDerivativeActions = missingActions.filter(
    (action) => action.workflow_type === 'free_derivatives',
  )

  async function loadFirstRunById() {
    if (!firstRunId.trim()) return
    setLoadingRun(true)
    setRunError(null)
    try {
      const response = await api.getFirstEvidenceRun(firstRunId.trim())
      setFirstRun(response)
    } catch (err) {
      setRunError(err instanceof Error ? err.message : 'First evidence run could not be loaded')
    } finally {
      setLoadingRun(false)
    }
  }

  async function loadBootstrapRunById() {
    if (!bootstrapRunId.trim()) return
    setLoadingBootstrap(true)
    setBootstrapError(null)
    try {
      const response = await api.getPublicDataBootstrapRun(bootstrapRunId.trim())
      setBootstrapRun(response)
    } catch (err) {
      setBootstrapError(err instanceof Error ? err.message : 'Bootstrap run could not be loaded')
    } finally {
      setLoadingBootstrap(false)
    }
  }

  async function loadFreeDerivativesRunById() {
    if (!freeDerivativesRunId.trim()) return
    setLoadingFreeDerivatives(true)
    setFreeDerivativesError(null)
    try {
      const response = await api.getFreeDerivativesRun(freeDerivativesRunId.trim())
      setFreeDerivativesRun(response)
    } catch (err) {
      setFreeDerivativesError(
        err instanceof Error
          ? err.message
          : 'Free derivatives bootstrap run could not be loaded',
      )
    } finally {
      setLoadingFreeDerivatives(false)
    }
  }

  async function runPublicBootstrap() {
    setLoadingBootstrap(true)
    setBootstrapError(null)
    try {
      const response = await api.runPublicDataBootstrap({
        include_binance: true,
        binance_symbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'],
        optional_binance_symbols: [],
        binance_timeframes: ['15m'],
        include_binance_open_interest: true,
        include_binance_funding: true,
        include_yahoo: true,
        yahoo_symbols: ['SPY', 'QQQ', 'GLD', 'GC=F'],
        yahoo_timeframes: ['1d'],
        days: 90,
        run_preflight_after: true,
        include_xau_local_instructions: true,
        research_only_acknowledged: true,
      })
      setBootstrapRun(response)
      setBootstrapRunId(response.bootstrap_run_id)
      const runs = await api.listPublicDataBootstrapRuns()
      setData((current) => (current ? { ...current, bootstrapRuns: runs } : current))
    } catch (err) {
      setBootstrapError(err instanceof Error ? err.message : 'Public bootstrap could not be started')
    } finally {
      setLoadingBootstrap(false)
    }
  }

  async function runLocalFirstEvidenceCheck() {
    setLoadingRun(true)
    setRunError(null)
    try {
      const response = await api.runFirstEvidenceRun({
        name: 'Dashboard local readiness check',
        preflight: {
          requested_capabilities: [
            'ohlcv',
            'open_interest',
            'funding',
            'iv',
            'gold_options_oi',
            'futures_oi',
            'xauusd_spot_execution',
          ],
          research_only_acknowledged: true,
        },
        use_existing_research_report_ids: [],
        use_existing_xau_report_id: null,
        run_when_partial: true,
        research_only_acknowledged: true,
      })
      setFirstRun(response)
      setFirstRunId(response.first_run_id)
    } catch (err) {
      setRunError(err instanceof Error ? err.message : 'First evidence run could not be started')
    } finally {
      setLoadingRun(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-sky-300">Research data onboarding</p>
          <h2 className="mt-1 text-xl font-semibold">Data Sources</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-400">
            Inspect public, local, optional paid, and forbidden source readiness before
            the first evidence workflow. Optional vendor keys are shown as presence only.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setLoading(true)
            setError(null)
            api.getDataSourceDashboardData()
              .then((response) => {
                setData(response)
                setFreeDerivativesRun(response.latestFreeDerivativesRun)
                setFreeDerivativesRunId(response.latestFreeDerivativesRun?.run_id ?? '')
              })
              .catch((err) =>
                setError(
                  err instanceof Error
                    ? err.message
                    : 'Data-source readiness could not be loaded',
                ),
              )
              .finally(() => setLoading(false))
          }}
          className="w-fit rounded-md border border-gray-700 px-3 py-2 text-sm text-gray-100 hover:border-sky-500"
        >
          Refresh readiness
        </button>
      </div>

      <ResearchOnlyNotice />

      {error && <Notice tone="error">{error}</Notice>}

      {loading ? (
        <EmptyState>Loading data-source readiness...</EmptyState>
      ) : data ? (
        <>
          <ReadinessSummary statuses={providerStatuses} data={data} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ReportSection title="Optional Provider Key Status">
              <OptionalProviderStatusTable statuses={optionalStatuses} />
            </ReportSection>
            <ReportSection title="Local XAU File Requirements">
              <XauSchemaPanel action={xauAction} />
            </ReportSection>
          </div>

          <ReportSection title="Free Public Derivatives">
            <FreeDerivativesPanel
              actions={freeDerivativeActions}
              capabilities={freeDerivativeCapabilities}
              error={freeDerivativesError}
              loading={loadingFreeDerivatives}
              onLoad={loadFreeDerivativesRunById}
              onRunIdChange={setFreeDerivativesRunId}
              run={freeDerivativesRun}
              runId={freeDerivativesRunId}
              runs={freeDerivativeRuns}
              statuses={freeDerivativeStatuses}
            />
          </ReportSection>

          <ReportSection title="Provider Capability Matrix">
            <CapabilityTable rows={capabilityRows} />
          </ReportSection>

          <ReportSection title="Missing Data Checklist">
            <MissingDataChecklist actions={missingActions} />
          </ReportSection>

          <ReportSection title="Public Data Bootstrap">
            <PublicBootstrapPanel
              bootstrapRun={bootstrapRun}
              bootstrapRunId={bootstrapRunId}
              bootstrapRuns={bootstrapRuns}
              loading={loadingBootstrap}
              error={bootstrapError}
              onBootstrapRunIdChange={setBootstrapRunId}
              onLoad={loadBootstrapRunById}
              onRun={runPublicBootstrap}
            />
          </ReportSection>

          <ReportSection title="First Evidence Run">
            <FirstEvidenceRunPanel
              firstRun={firstRun}
              firstRunId={firstRunId}
              loading={loadingRun}
              error={runError}
              onFirstRunIdChange={setFirstRunId}
              onLoad={loadFirstRunById}
              onRun={runLocalFirstEvidenceCheck}
            />
          </ReportSection>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ReportSection title="Readiness Limitations">
              <NotesList
                notes={uniqueValues(providerStatuses.flatMap((status) => status.limitations))}
                emptyText="No provider limitations reported."
              />
            </ReportSection>
            <ReportSection title="Research-Only Warnings">
              <NotesList
                notes={data.readiness.research_only_warnings}
                emptyText="No research-only warnings reported."
              />
            </ReportSection>
          </div>
        </>
      ) : (
        <EmptyState>No readiness snapshot is available.</EmptyState>
      )}
    </div>
  )
}

function ReadinessSummary({
  data,
  statuses,
}: {
  data: DataSourceDashboardData
  statuses: DataSourceProviderStatus[]
}) {
  const publicCount = statuses.filter(
    (status) => status.capabilities.tier === 'tier_0_public_local',
  ).length
  const optionalConfigured = statuses.filter(
    (status) => status.capabilities.is_optional && status.configured,
  ).length
  const optionalMissing = statuses.filter(
    (status) => status.capabilities.is_optional && !status.configured,
  ).length
  const forbiddenCount = statuses.filter((status) => status.status === 'forbidden').length

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <SummaryCard
        label="Public/local"
        value={data.readiness.public_sources_available ? `${publicCount} available` : 'blocked'}
      />
      <SummaryCard label="Optional configured" value={optionalConfigured} />
      <SummaryCard label="Optional missing" value={optionalMissing} />
      <SummaryCard label="Forbidden categories" value={forbiddenCount} />
    </div>
  )
}

function OptionalProviderStatusTable({ statuses }: { statuses: DataSourceProviderStatus[] }) {
  if (statuses.length === 0) {
    return <EmptyInline>No optional provider statuses are available.</EmptyInline>
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-gray-700 text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Provider</th>
            <th className="px-3 py-2">Key status</th>
            <th className="px-3 py-2">Variable</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {statuses.map((status) => (
            <tr key={status.provider_type}>
              <td className="px-3 py-2 font-medium">{status.capabilities.display_name}</td>
              <td className="px-3 py-2">
                <StatusPill status={status.configured ? 'configured' : 'missing'} />
              </td>
              <td className="px-3 py-2 text-gray-300">{status.env_var_name ?? 'n/a'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs leading-5 text-gray-400">
        Only presence is displayed. Secret values, masked values, partial values, and hashes
        are never returned by this page.
      </p>
    </div>
  )
}

function XauSchemaPanel({ action }: { action: DataSourceMissingDataAction | undefined }) {
  if (!action) {
    return <EmptyInline>No XAU local-file requirement action is available.</EmptyInline>
  }

  return (
    <div className="space-y-4 text-sm">
      <div>
        <div className="text-xs uppercase text-gray-400">Required columns</div>
        <ChipList items={action.required_columns} tone="warning" emptyText="None" />
      </div>
      <div>
        <div className="text-xs uppercase text-gray-400">Optional columns</div>
        <ChipList items={action.optional_columns} tone="neutral" emptyText="None" />
      </div>
      <NotesList notes={action.instructions} emptyText="No XAU import instructions." />
    </div>
  )
}

function FreeDerivativesPanel({
  actions,
  capabilities,
  error,
  loading,
  onLoad,
  onRunIdChange,
  run,
  runId,
  runs,
  statuses,
}: {
  actions: DataSourceMissingDataAction[]
  capabilities: DataSourceCapability[]
  error: string | null
  loading: boolean
  onLoad: () => void
  onRunIdChange: (value: string) => void
  run: FreeDerivativesBootstrapRun | null
  runId: string
  runs: FreeDerivativesBootstrapRunSummary[]
  statuses: DataSourceProviderStatus[]
}) {
  const runWarnings = run
    ? uniqueValues([
        ...run.warnings,
        ...run.research_only_warnings,
        ...run.source_results.flatMap((result) => result.warnings),
      ])
    : []
  const runLimitations = run
    ? uniqueValues([
        ...run.limitations,
        ...run.source_results.flatMap((result) => result.limitations),
      ])
    : []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryCard label="Sources" value={statuses.length} />
        <SummaryCard label="Saved runs" value={runs.length} />
        <SummaryCard label="Selected run" value={run?.run_id ?? runs[0]?.run_id ?? 'none'} />
        <SummaryCard label="Scope" value="research only" />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {statuses.map((status) => (
          <MiniPanel key={status.provider_type} title={status.capabilities.display_name}>
            <div className="mb-3">
              <StatusPill status={status.status} />
            </div>
            <NotesList notes={status.limitations} emptyText="No limitations reported." compact />
          </MiniPanel>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto]">
        <select
          value={runId}
          onChange={(event) => onRunIdChange(event.target.value)}
          className="rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
        >
          <option value="">Select free derivatives run</option>
          {runs.map((summary) => (
            <option key={summary.run_id} value={summary.run_id}>
              {summary.run_id} | {summary.status}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onLoad}
          disabled={loading || !runId.trim()}
          className="rounded-md border border-gray-700 px-3 py-2 text-sm text-gray-100 hover:border-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Load run
        </button>
      </div>

      {error && <Notice tone="error">{error}</Notice>}
      {loading && <EmptyInline>Loading free derivatives run...</EmptyInline>}

      {run ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <SummaryCard label="Status" value={run.status} />
            <SummaryCard label="Sources" value={run.source_results.length} />
            <SummaryCard label="Artifacts" value={run.artifacts.length} />
            <SummaryCard label="Completed" value={run.completed_at ?? 'n/a'} />
          </div>

          <FreeDerivativesSourceTable results={run.source_results} />
          <FreeDerivativesArtifactTable artifacts={run.artifacts} />

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <MiniPanel title="Run warnings">
              <NotesList notes={runWarnings} emptyText="No warnings reported." compact />
            </MiniPanel>
            <MiniPanel title="Run limitations">
              <NotesList notes={runLimitations} emptyText="No limitations reported." compact />
            </MiniPanel>
          </div>

          <MiniPanel title="Run missing-data actions">
            <NotesList
              notes={run.missing_data_actions}
              emptyText="No run-specific missing-data actions."
              compact
            />
          </MiniPanel>
        </div>
      ) : (
        <EmptyInline>No free derivatives run is loaded.</EmptyInline>
      )}

      <MiniPanel title="Capabilities">
        <CapabilityTable rows={capabilities} />
      </MiniPanel>

      <MiniPanel title="Missing-data actions">
        <MissingDataChecklist actions={actions} />
      </MiniPanel>

      <p className="text-xs leading-5 text-gray-400">
        CFTC, GVZ, and Deribit entries are public/no-key research data only. This page
        does not return secret values, masked values, partial credentials, private
        account endpoints, or order endpoints; generated outputs stay under ignored
        data/raw, data/processed, and data/reports paths.
      </p>
    </div>
  )
}

function FreeDerivativesSourceTable({ results }: { results: FreeDerivativesSourceResult[] }) {
  if (results.length === 0) {
    return (
      <MiniPanel title="Source status">
        <EmptyInline>No source results are available.</EmptyInline>
      </MiniPanel>
    )
  }

  return (
    <MiniPanel title="Source status">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-gray-700 text-xs uppercase text-gray-400">
            <tr>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Rows</th>
              <th className="px-3 py-2">Instruments</th>
              <th className="px-3 py-2">Coverage</th>
              <th className="px-3 py-2">Snapshot</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {results.map((result) => (
              <tr key={result.source}>
                <td className="px-3 py-2 font-medium">{formatValue(result.source)}</td>
                <td className="px-3 py-2">
                  <StatusPill status={result.status} />
                </td>
                <td className="px-3 py-2 text-gray-300">{result.row_count}</td>
                <td className="px-3 py-2 text-gray-300">{result.instrument_count}</td>
                <td className="px-3 py-2 text-gray-300">
                  {result.coverage_start ?? 'n/a'} to {result.coverage_end ?? 'n/a'}
                </td>
                <td className="px-3 py-2 text-gray-300">
                  {result.snapshot_timestamp ?? 'n/a'}
                </td>
                <td className="min-w-80 px-3 py-2 text-gray-300">
                  <NotesList
                    notes={result.missing_data_actions}
                    emptyText="None"
                    compact
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </MiniPanel>
  )
}

function FreeDerivativesArtifactTable({
  artifacts,
}: {
  artifacts: FreeDerivativesArtifact[]
}) {
  if (artifacts.length === 0) {
    return (
      <MiniPanel title="Output paths">
        <EmptyInline>No artifacts were written.</EmptyInline>
      </MiniPanel>
    )
  }

  return (
    <MiniPanel title="Output paths">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-gray-700 text-xs uppercase text-gray-400">
            <tr>
              <th className="px-3 py-2">Artifact</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Format</th>
              <th className="px-3 py-2">Rows</th>
              <th className="px-3 py-2">Path</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {artifacts.map((artifact) => (
              <tr key={`${artifact.artifact_type}-${artifact.path}`}>
                <td className="px-3 py-2 font-medium">{formatValue(artifact.artifact_type)}</td>
                <td className="px-3 py-2 text-gray-300">{formatValue(artifact.source)}</td>
                <td className="px-3 py-2 text-gray-300">{artifact.format}</td>
                <td className="px-3 py-2 text-gray-300">{artifact.rows ?? 'n/a'}</td>
                <td className="max-w-sm break-all px-3 py-2 text-gray-300">
                  {artifact.path}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </MiniPanel>
  )
}

function CapabilityTable({ rows }: { rows: DataSourceCapability[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-gray-700 text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Provider</th>
            <th className="px-3 py-2">Tier</th>
            <th className="px-3 py-2">Supported</th>
            <th className="px-3 py-2">Unsupported</th>
            <th className="px-3 py-2">Requirements</th>
            <th className="px-3 py-2">Limitations</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {rows.map((row) => (
            <tr key={row.provider_type}>
              <td className="px-3 py-2 font-medium">{row.display_name}</td>
              <td className="px-3 py-2 text-gray-300">{formatValue(row.tier)}</td>
              <td className="px-3 py-2">
                <ChipList items={row.supports} tone="success" emptyText="None" />
              </td>
              <td className="px-3 py-2">
                <ChipList items={row.unsupported} tone="warning" emptyText="None" />
              </td>
              <td className="px-3 py-2 text-gray-300">
                {[
                  row.requires_key ? 'key presence' : null,
                  row.requires_local_file ? 'local file' : null,
                  row.is_optional ? 'optional' : null,
                  row.forbidden_reason ? 'forbidden' : null,
                ]
                  .filter(Boolean)
                  .join(', ') || 'public/no-key'}
              </td>
              <td className="min-w-80 px-3 py-2 text-gray-300">
                <NotesList notes={row.limitations} emptyText="None" compact />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MissingDataChecklist({ actions }: { actions: DataSourceMissingDataAction[] }) {
  if (actions.length === 0) {
    return <EmptyInline>No missing-data actions are currently reported.</EmptyInline>
  }

  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      {actions.map((action) => (
        <div key={action.action_id} className="rounded-md border border-gray-700 p-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-medium text-white">{action.title}</p>
              <p className="mt-1 text-xs text-gray-400">
                {formatValue(action.workflow_type)} | {action.asset ?? action.provider_type}
              </p>
            </div>
            <StatusPill status={action.blocking ? 'blocking' : action.severity} />
          </div>
          <NotesList notes={action.instructions} emptyText="No instructions." compact />
        </div>
      ))}
    </div>
  )
}

function PublicBootstrapPanel({
  bootstrapRun,
  bootstrapRunId,
  bootstrapRuns,
  error,
  loading,
  onBootstrapRunIdChange,
  onLoad,
  onRun,
}: {
  bootstrapRun: DataSourceBootstrapRunResult | null
  bootstrapRunId: string
  bootstrapRuns: DataSourceBootstrapRunResult[]
  error: string | null
  loading: boolean
  onBootstrapRunIdChange: (value: string) => void
  onLoad: () => void
  onRun: () => void
}) {
  const downloaded = bootstrapRun?.asset_summaries.filter((asset) => asset.status === 'completed') ?? []
  const blocked = bootstrapRun?.asset_summaries.filter((asset) => asset.status !== 'completed') ?? []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto_auto]">
        <select
          value={bootstrapRunId}
          onChange={(event) => onBootstrapRunIdChange(event.target.value)}
          className="rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
        >
          <option value="">Select bootstrap run</option>
          {bootstrapRuns.map((run) => (
            <option key={run.bootstrap_run_id} value={run.bootstrap_run_id}>
              {run.bootstrap_run_id} | {run.status}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onLoad}
          disabled={loading || !bootstrapRunId.trim()}
          className="rounded-md border border-gray-700 px-3 py-2 text-sm text-gray-100 hover:border-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Load bootstrap
        </button>
        <button
          type="button"
          onClick={onRun}
          disabled={loading}
          className="rounded-md border border-sky-700 bg-sky-950 px-3 py-2 text-sm text-sky-100 hover:border-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Run public bootstrap
        </button>
      </div>

      <p className="text-xs leading-5 text-gray-400">
        Public bootstrap uses no private trading keys and no paid vendor keys. It may call
        public Binance and Yahoo endpoints only when this button is explicitly used.
      </p>

      {error && <Notice tone="error">{error}</Notice>}
      {loading && <EmptyInline>Loading public bootstrap run...</EmptyInline>}

      {bootstrapRun ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <SummaryCard label="Status" value={bootstrapRun.status} />
            <SummaryCard label="Downloaded" value={downloaded.length} />
            <SummaryCard label="Blocked/skipped" value={blocked.length} />
            <SummaryCard label="Bootstrap run" value={bootstrapRun.bootstrap_run_id} />
          </div>

          <BootstrapAssetTable title="Downloaded Assets" assets={downloaded} />
          <BootstrapAssetTable title="Skipped Or Failed Assets" assets={blocked} />

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <MiniPanel title="Bootstrap warnings">
              <NotesList
                notes={[
                  ...bootstrapRun.research_only_warnings,
                  ...bootstrapRun.asset_summaries.flatMap((asset) => asset.warnings),
                ]}
                emptyText="No bootstrap warnings."
                compact
              />
            </MiniPanel>
            <MiniPanel title="Bootstrap limitations">
              <NotesList
                notes={[
                  ...bootstrapRun.limitations,
                  ...bootstrapRun.asset_summaries.flatMap((asset) => asset.limitations),
                ]}
                emptyText="No bootstrap limitations."
                compact
              />
            </MiniPanel>
          </div>

          <MiniPanel title="Bootstrap missing data actions">
            <MissingDataChecklist actions={bootstrapRun.missing_data_actions} />
          </MiniPanel>

          {bootstrapRun.preflight_result ? (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <SummaryCard label="Preflight" value={bootstrapRun.preflight_result.status} />
              <SummaryCard
                label="Crypto ready"
                value={
                  bootstrapRun.preflight_result.crypto_results.filter(
                    (asset) => asset.status === 'ready',
                  ).length
                }
              />
              <SummaryCard
                label="Proxy ready"
                value={
                  bootstrapRun.preflight_result.proxy_results.filter(
                    (asset) => asset.status === 'ready',
                  ).length
                }
              />
              <SummaryCard
                label="XAU status"
                value={bootstrapRun.preflight_result.xau_result?.status ?? 'n/a'}
              />
            </div>
          ) : null}
        </div>
      ) : (
        <EmptyInline>No public bootstrap run is loaded.</EmptyInline>
      )}
    </div>
  )
}

function BootstrapAssetTable({
  assets,
  title,
}: {
  assets: DataSourceBootstrapAssetSummary[]
  title: string
}) {
  if (assets.length === 0) {
    return (
      <MiniPanel title={title}>
        <EmptyInline>No rows.</EmptyInline>
      </MiniPanel>
    )
  }

  return (
    <MiniPanel title={title}>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-gray-700 text-xs uppercase text-gray-400">
            <tr>
              <th className="px-3 py-2">Asset</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Rows</th>
              <th className="px-3 py-2">Processed output</th>
              <th className="px-3 py-2">Unsupported</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {assets.map((asset) => (
              <tr key={`${asset.provider_type}-${asset.symbol}-${asset.timeframe}`}>
                <td className="px-3 py-2 font-medium">
                  {asset.symbol} {asset.timeframe}
                </td>
                <td className="px-3 py-2 text-gray-300">{formatValue(asset.provider_type)}</td>
                <td className="px-3 py-2 text-gray-300">{asset.row_count}</td>
                <td className="max-w-xs break-all px-3 py-2 text-gray-300">
                  {asset.processed_feature_path ?? 'n/a'}
                </td>
                <td className="px-3 py-2">
                  <ChipList
                    items={asset.unsupported_capabilities}
                    tone="warning"
                    emptyText="None"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </MiniPanel>
  )
}

function FirstEvidenceRunPanel({
  error,
  firstRun,
  firstRunId,
  loading,
  onFirstRunIdChange,
  onLoad,
  onRun,
}: {
  error: string | null
  firstRun: FirstEvidenceRunResult | null
  firstRunId: string
  loading: boolean
  onFirstRunIdChange: (value: string) => void
  onLoad: () => void
  onRun: () => void
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto_auto]">
        <input
          value={firstRunId}
          onChange={(event) => onFirstRunIdChange(event.target.value)}
          placeholder="first_run_id"
          className="rounded-md border border-gray-700 bg-gray-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
        />
        <button
          type="button"
          onClick={onLoad}
          disabled={loading || !firstRunId.trim()}
          className="rounded-md border border-gray-700 px-3 py-2 text-sm text-gray-100 hover:border-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Load run
        </button>
        <button
          type="button"
          onClick={onRun}
          disabled={loading}
          className="rounded-md border border-sky-700 bg-sky-950 px-3 py-2 text-sm text-sky-100 hover:border-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Run local check
        </button>
      </div>

      <p className="text-xs leading-5 text-gray-400">
        The local check calls the first-run endpoint with research-only acknowledgement
        and performs local readiness checks only. It does not fetch external data.
      </p>

      {error && <Notice tone="error">{error}</Notice>}
      {loading && <EmptyInline>Loading first evidence run...</EmptyInline>}

      {firstRun ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <SummaryCard label="Status" value={firstRun.status} />
            <SummaryCard label="Decision" value={firstRun.decision ?? 'n/a'} />
            <SummaryCard label="First run" value={firstRun.first_run_id} />
            <SummaryCard label="Execution run" value={firstRun.execution_run_id ?? 'n/a'} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <MiniPanel title="Research report IDs">
              <NotesList notes={firstRun.linked_research_report_ids} emptyText="None" compact />
            </MiniPanel>
            <MiniPanel title="XAU report IDs">
              <NotesList notes={firstRun.linked_xau_report_ids} emptyText="None" compact />
            </MiniPanel>
            <MiniPanel title="Evidence path">
              <p className="break-all text-sm text-gray-300">
                {firstRun.evidence_report_path ?? 'n/a'}
              </p>
            </MiniPanel>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <MiniPanel title="First-run missing data">
              <MissingDataChecklist actions={firstRun.missing_data_actions} />
            </MiniPanel>
            <MiniPanel title="First-run warnings">
              <NotesList
                notes={firstRun.research_only_warnings}
                emptyText="No warnings."
                compact
              />
            </MiniPanel>
          </div>
        </div>
      ) : (
        <EmptyInline>No first evidence run is loaded.</EmptyInline>
      )}
    </div>
  )
}

function ResearchOnlyNotice() {
  return (
    <Notice tone="warning">
      Data-source onboarding and first-run evidence are research-only. This page does not
      enable live trading, paper trading, shadow trading, broker integration, private
      trading keys, wallet handling, or order execution.
    </Notice>
  )
}

function ReportSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md bg-gray-800 p-4">
      <h3 className="mb-4 text-base font-semibold">{title}</h3>
      {children}
    </section>
  )
}

function MiniPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-gray-700 p-3">
      <h4 className="mb-3 text-sm font-semibold text-gray-200">{title}</h4>
      {children}
    </div>
  )
}

function SummaryCard({ label, value }: { label: number | string; value: number | string }) {
  return (
    <div className="rounded-md bg-gray-800 p-4">
      <div className="text-xs uppercase text-gray-400">{label}</div>
      <div className="mt-1 break-words text-lg font-semibold text-white">{value}</div>
    </div>
  )
}

function Notice({ tone, children }: { tone: 'warning' | 'error'; children: ReactNode }) {
  const toneClass =
    tone === 'error'
      ? 'border-red-900 bg-red-950 text-red-200'
      : 'border-amber-900 bg-amber-950 text-amber-100'
  return <div className={`rounded-md border p-4 text-sm leading-6 ${toneClass}`}>{children}</div>
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === 'configured' || status === 'ready' || status === 'completed'
      ? 'border-emerald-700 bg-emerald-950 text-emerald-200'
      : status === 'forbidden' || status === 'blocking' || status === 'blocked' || status === 'failed'
        ? 'border-red-800 bg-red-950 text-red-200'
        : 'border-amber-800 bg-amber-950 text-amber-100'
  return (
    <span className={`inline-flex rounded-full border px-2 py-1 text-xs font-medium ${tone}`}>
      {formatValue(status)}
    </span>
  )
}

function ChipList({
  emptyText,
  items,
  tone,
}: {
  emptyText: string
  items: string[]
  tone: 'success' | 'warning' | 'neutral'
}) {
  if (items.length === 0) {
    return <span className="text-sm text-gray-500">{emptyText}</span>
  }
  const toneClass =
    tone === 'success'
      ? 'border-emerald-800 bg-emerald-950 text-emerald-200'
      : tone === 'warning'
        ? 'border-amber-800 bg-amber-950 text-amber-100'
        : 'border-gray-700 bg-gray-900 text-gray-300'
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span key={item} className={`rounded-full border px-2 py-1 text-xs ${toneClass}`}>
          {formatValue(item)}
        </span>
      ))}
    </div>
  )
}

function NotesList({
  compact = false,
  emptyText,
  notes,
}: {
  compact?: boolean
  emptyText: string
  notes: string[]
}) {
  const values = uniqueValues(notes)
  if (values.length === 0) {
    return <p className="text-sm text-gray-500">{emptyText}</p>
  }
  return (
    <ul className={compact ? 'mt-3 space-y-1 text-sm text-gray-300' : 'space-y-2 text-sm text-gray-300'}>
      {values.map((note) => (
        <li key={note} className="leading-6">
          {note}
        </li>
      ))}
    </ul>
  )
}

function EmptyState({ children }: { children: ReactNode }) {
  return <section className="rounded-md bg-gray-800 p-4 text-sm text-gray-300">{children}</section>
}

function EmptyInline({ children }: { children: ReactNode }) {
  return <p className="text-sm text-gray-400">{children}</p>
}

function dedupeActions(actions: DataSourceMissingDataAction[]) {
  const seen = new Set<string>()
  return actions.filter((action) => {
    if (seen.has(action.action_id)) return false
    seen.add(action.action_id)
    return true
  })
}

function uniqueValues(values: string[]) {
  return values.filter((value, index, array) => Boolean(value) && array.indexOf(value) === index)
}

function formatValue(value: string) {
  return value.replaceAll('_', ' ')
}
