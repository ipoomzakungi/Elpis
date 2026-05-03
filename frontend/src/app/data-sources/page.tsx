'use client'

import { type ReactNode, useEffect, useMemo, useState } from 'react'

import { api } from '@/services/api'
import {
  DataSourceCapability,
  DataSourceDashboardData,
  DataSourceMissingDataAction,
  DataSourceProviderStatus,
  FirstEvidenceRunResult,
} from '@/types'

const OPTIONAL_PROVIDER_TYPES = new Set([
  'kaiko_optional',
  'tardis_optional',
  'coinglass_optional',
  'cryptoquant_optional',
  'cme_quikstrike_local_or_optional',
])

export default function DataSourcesPage() {
  const [data, setData] = useState<DataSourceDashboardData | null>(null)
  const [firstRun, setFirstRun] = useState<FirstEvidenceRunResult | null>(null)
  const [firstRunId, setFirstRunId] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingRun, setLoadingRun] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    api.getDataSourceDashboardData()
      .then((response) => {
        if (!active) return
        setData(response)
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
  const optionalStatuses = providerStatuses.filter((status) =>
    OPTIONAL_PROVIDER_TYPES.has(status.provider_type),
  )
  const defaultMissingActions = data?.missingData.actions ?? []
  const readinessMissingActions = data?.readiness.missing_data_actions ?? []
  const missingActions = useMemo(
    () => dedupeActions([...readinessMissingActions, ...defaultMissingActions]),
    [readinessMissingActions, defaultMissingActions],
  )
  const xauAction = missingActions.find((action) => action.workflow_type === 'xau_vol_oi')

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
              .then(setData)
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

          <ReportSection title="Provider Capability Matrix">
            <CapabilityTable rows={capabilityRows} />
          </ReportSection>

          <ReportSection title="Missing Data Checklist">
            <MissingDataChecklist actions={missingActions} />
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
      : status === 'forbidden' || status === 'blocking' || status === 'blocked'
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
