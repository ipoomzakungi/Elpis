'use client'

import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { api } from '@/services/api'
import {
  ConcentrationAssetRow,
  RegimeCoverageAssetRow,
  ResearchAssetResult,
  ResearchDashboardData,
  ResearchRunSummary,
  StressSurvivalRow,
  StrategyComparisonRow,
  WalkForwardStabilityRow,
} from '@/types'

export default function ResearchPage() {
  const [runs, setRuns] = useState<ResearchRunSummary[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [dashboardData, setDashboardData] = useState<ResearchDashboardData | null>(null)
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [loadingReport, setLoadingReport] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoadingRuns(true)
    api.getResearchReports()
      .then((response) => {
        if (!active) return
        setRuns(response.runs)
        setSelectedRunId((current) => current ?? response.runs[0]?.research_run_id ?? null)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Research reports could not be loaded')
      })
      .finally(() => {
        if (active) setLoadingRuns(false)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedRunId) {
      setDashboardData(null)
      return
    }

    let active = true
    setLoadingReport(true)
    setError(null)
    api.getResearchDashboardData(selectedRunId)
      .then((response) => {
        if (!active) return
        setDashboardData(response)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Research report could not be loaded')
        setDashboardData(null)
      })
      .finally(() => {
        if (active) setLoadingReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedRunId])

  const selectedSummary = useMemo(
    () => runs.find((item) => item.research_run_id === selectedRunId) ?? null,
    [runs, selectedRunId],
  )

  const assets = dashboardData?.assets.data ?? dashboardData?.run.assets ?? []
  const blockedAssets = assets.filter((asset) => asset.status === 'blocked')
  const limitationNotes = uniqueValues([
    ...(dashboardData?.run.limitations ?? []),
    ...assets.flatMap((asset) => asset.limitations),
    ...assets.flatMap((asset) => asset.preflight.capability_snapshot.limitation_notes),
  ])
  const warningNotes = uniqueValues([
    ...(dashboardData?.run.warnings ?? []),
    ...assets.flatMap((asset) => asset.warnings),
    ...assets.flatMap((asset) => asset.preflight.warnings),
  ])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-xl font-semibold">Research Reports</h2>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-400">
              {selectedSummary.research_run_id} | {selectedSummary.status} |{' '}
              {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Research run
          <select
            value={selectedRunId ?? ''}
            onChange={(event) => setSelectedRunId(event.target.value || null)}
            className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingRuns || runs.length === 0}
          >
            {runs.length === 0 ? (
              <option value="">No research reports</option>
            ) : (
              runs.map((item) => (
                <option key={item.research_run_id} value={item.research_run_id}>
                  {item.research_run_id}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      <ResearchOnlyNotice />

      {error && <Notice tone="error">{error}</Notice>}

      {loadingRuns ? (
        <EmptyState>Loading research reports...</EmptyState>
      ) : runs.length === 0 ? (
        <EmptyState>No grouped research reports are available.</EmptyState>
      ) : loadingReport ? (
        <EmptyState>Loading grouped report...</EmptyState>
      ) : dashboardData ? (
        <>
          <StatusSummary
            assetCount={assets.length}
            completedCount={dashboardData.run.completed_count}
            blockedCount={dashboardData.run.blocked_count}
            status={dashboardData.run.status}
          />

          <ReportSection title="Assets">
            <AssetSummaryTable assets={assets} />
          </ReportSection>

          {(blockedAssets.length > 0 || warningNotes.length > 0 || limitationNotes.length > 0) && (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <ReportSection title="Missing Data And Warnings">
                <MissingDataPanel blockedAssets={blockedAssets} warnings={warningNotes} />
              </ReportSection>
              <ReportSection title="Source Limitations">
                <NotesList notes={limitationNotes} emptyText="No source limitation notes" />
              </ReportSection>
            </div>
          )}

          <ReportSection title="Strategy Vs Baseline Comparison">
            <ComparisonTable rows={dashboardData.comparison.data} />
          </ReportSection>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ReportSection title="Stress Survival">
              <StressTable rows={dashboardData.validation.stress} />
            </ReportSection>
            <ReportSection title="Walk-Forward Stability">
              <WalkForwardTable rows={dashboardData.validation.walk_forward} />
            </ReportSection>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ReportSection title="Regime Coverage">
              <RegimeCoverageTable rows={dashboardData.validation.regime_coverage} />
            </ReportSection>
            <ReportSection title="Trade Concentration">
              <ConcentrationTable rows={dashboardData.validation.concentration} />
            </ReportSection>
          </div>
        </>
      ) : null}
    </div>
  )
}

function ResearchOnlyNotice() {
  return (
    <Notice tone="warning">
      Grouped research reports are historical research outputs only. They are not
      profitability evidence, predictive proof, safety evidence, or live-readiness evidence.
    </Notice>
  )
}

function StatusSummary({
  assetCount,
  blockedCount,
  completedCount,
  status,
}: {
  assetCount: number
  blockedCount: number
  completedCount: number
  status: string
}) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <SummaryCard label="Status" value={status} />
      <SummaryCard label="Assets" value={assetCount} />
      <SummaryCard label="Completed" value={completedCount} />
      <SummaryCard label="Blocked" value={blockedCount} />
    </div>
  )
}

function SummaryCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md bg-gray-800 p-4">
      <div className="text-xs uppercase text-gray-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
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

function Notice({ tone, children }: { tone: 'warning' | 'error'; children: ReactNode }) {
  const toneClass =
    tone === 'error'
      ? 'border-red-900 bg-red-950 text-red-200'
      : 'border-amber-900 bg-amber-950 text-amber-100'
  return <div className={`rounded-md border px-4 py-3 text-sm ${toneClass}`}>{children}</div>
}

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="rounded-md bg-gray-800 p-4 text-sm text-gray-400">{children}</div>
}

function AssetSummaryTable({ assets }: { assets: ResearchAssetResult[] }) {
  if (assets.length === 0) {
    return <p className="text-sm text-gray-400">No assets in this report.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Asset</th>
            <th className="px-3 py-2">Provider</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Classification</th>
            <th className="px-3 py-2">Capabilities</th>
            <th className="px-3 py-2">Rows</th>
            <th className="px-3 py-2">Date Range</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {assets.map((asset) => {
            const capability = asset.preflight.capability_snapshot
            return (
              <tr key={`${asset.provider}-${asset.symbol}`}>
                <td className="px-3 py-2 font-medium text-white">{asset.symbol}</td>
                <td className="px-3 py-2">{asset.provider}</td>
                <td className="px-3 py-2">{asset.status}</td>
                <td className="px-3 py-2">{asset.classification}</td>
                <td className="px-3 py-2">
                  <div className="flex min-w-72 flex-wrap gap-2">
                    <CapabilityBadge
                      label="OHLCV"
                      state={capability.detected_ohlcv ? 'available' : 'missing'}
                    />
                    <CapabilityBadge
                      label="Regime"
                      state={capability.detected_regime ? 'available' : 'missing'}
                    />
                    <CapabilityBadge
                      label="OI"
                      state={capabilityState(
                        capability.supports_open_interest,
                        capability.detected_open_interest,
                      )}
                    />
                    <CapabilityBadge
                      label="Funding"
                      state={capabilityState(
                        capability.supports_funding_rate,
                        capability.detected_funding_rate,
                      )}
                    />
                  </div>
                </td>
                <td className="px-3 py-2">{formatValue(asset.preflight.row_count)}</td>
                <td className="px-3 py-2">
                  {formatDateRange(asset.preflight.first_timestamp, asset.preflight.last_timestamp)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CapabilityBadge({
  label,
  state,
}: {
  label: string
  state: 'available' | 'missing' | 'unsupported'
}) {
  const stateClass =
    state === 'available'
      ? 'border-emerald-700 bg-emerald-950 text-emerald-200'
      : state === 'unsupported'
        ? 'border-gray-700 bg-gray-950 text-gray-400'
        : 'border-yellow-700 bg-yellow-950 text-yellow-200'
  return (
    <span className={`rounded border px-2 py-1 text-xs ${stateClass}`}>
      {label}: {state}
    </span>
  )
}

function MissingDataPanel({
  blockedAssets,
  warnings,
}: {
  blockedAssets: ResearchAssetResult[]
  warnings: string[]
}) {
  if (blockedAssets.length === 0 && warnings.length === 0) {
    return <p className="text-sm text-gray-400">No missing-data warnings.</p>
  }

  return (
    <div className="space-y-4 text-sm">
      {blockedAssets.map((asset) => (
        <div key={`${asset.provider}-${asset.symbol}`} className="space-y-2">
          <div className="font-medium text-white">
            {asset.symbol} is blocked: {asset.preflight.status}
          </div>
          <NotesList
            notes={[...asset.preflight.instructions, ...asset.preflight.warnings]}
            emptyText="No instructions supplied"
          />
        </div>
      ))}
      {warnings.length > 0 && <NotesList notes={warnings} emptyText="No warnings" />}
    </div>
  )
}

function NotesList({ notes, emptyText }: { notes: string[]; emptyText: string }) {
  if (notes.length === 0) {
    return <p className="text-sm text-gray-400">{emptyText}</p>
  }

  return (
    <ul className="space-y-1 text-sm text-gray-300">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  )
}

function ComparisonTable({ rows }: { rows: StrategyComparisonRow[] }) {
  return (
    <DataTable
      emptyText="No strategy comparison rows."
      rows={rows}
      columns={[
        { key: 'symbol', label: 'Asset' },
        { key: 'provider', label: 'Provider' },
        { key: 'mode', label: 'Mode' },
        { key: 'category', label: 'Category' },
        { key: 'total_return_pct', label: 'Return %', format: formatNumber },
        { key: 'max_drawdown_pct', label: 'Max DD %', format: formatNumber },
        { key: 'number_of_trades', label: 'Trades' },
        { key: 'profit_factor', label: 'Profit Factor', format: formatNumber },
        { key: 'win_rate', label: 'Win Rate', format: formatPercentRatio },
      ]}
    />
  )
}

function StressTable({ rows }: { rows: StressSurvivalRow[] }) {
  return (
    <DataTable
      emptyText="No stress survival rows."
      rows={rows}
      columns={[
        { key: 'symbol', label: 'Asset' },
        { key: 'mode', label: 'Mode' },
        { key: 'profile', label: 'Profile' },
        { key: 'outcome', label: 'Outcome' },
        { key: 'survived', label: 'Survived', format: formatBoolean },
      ]}
    />
  )
}

function WalkForwardTable({ rows }: { rows: WalkForwardStabilityRow[] }) {
  return (
    <DataTable
      emptyText="No walk-forward rows."
      rows={rows}
      columns={[
        { key: 'symbol', label: 'Asset' },
        { key: 'split_id', label: 'Split' },
        { key: 'status', label: 'Status' },
        { key: 'row_count', label: 'Rows' },
        { key: 'trade_count', label: 'Trades' },
        { key: 'stable', label: 'Stable', format: formatBoolean },
      ]}
    />
  )
}

function RegimeCoverageTable({ rows }: { rows: RegimeCoverageAssetRow[] }) {
  return (
    <DataTable
      emptyText="No regime coverage rows."
      rows={rows}
      columns={[
        { key: 'symbol', label: 'Asset' },
        { key: 'regime', label: 'Regime' },
        { key: 'bar_count', label: 'Bars' },
        { key: 'trade_count', label: 'Trades' },
        { key: 'return_pct', label: 'Return %', format: formatNumber },
      ]}
    />
  )
}

function ConcentrationTable({ rows }: { rows: ConcentrationAssetRow[] }) {
  return (
    <DataTable
      emptyText="No concentration rows."
      rows={rows}
      columns={[
        { key: 'symbol', label: 'Asset' },
        { key: 'warning_level', label: 'Warning' },
        { key: 'top_1_profit_contribution_pct', label: 'Top 1 %', format: formatNumber },
        { key: 'top_5_profit_contribution_pct', label: 'Top 5 %', format: formatNumber },
        { key: 'top_10_profit_contribution_pct', label: 'Top 10 %', format: formatNumber },
        { key: 'max_consecutive_losses', label: 'Max Loss Streak' },
        { key: 'drawdown_recovery_status', label: 'Recovery' },
      ]}
    />
  )
}

interface DataColumn {
  key: string
  label: string
  format?: (value: unknown) => string
}

function DataTable({
  columns,
  emptyText,
  rows,
}: {
  columns: DataColumn[]
  emptyText: string
  rows: object[]
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">{emptyText}</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="px-3 py-2">
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {rows.map((row, index) => {
            const values = row as Record<string, unknown>
            return (
              <tr key={String(values[columns[0].key] ?? index)}>
                {columns.map((column) => (
                  <td key={column.key} className="px-3 py-2">
                    {column.format ? column.format(values[column.key]) : formatValue(values[column.key])}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function capabilityState(
  supported: boolean,
  detected: boolean,
): 'available' | 'missing' | 'unsupported' {
  if (!supported) return 'unsupported'
  return detected ? 'available' : 'missing'
}

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)))
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'n/a'
  if (typeof value === 'number') return formatNumber(value)
  if (typeof value === 'boolean') return formatBoolean(value)
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

function formatNumber(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'n/a'
  return value.toFixed(2)
}

function formatPercentRatio(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'n/a'
  return `${(value * 100).toFixed(2)}%`
}

function formatBoolean(value: unknown): string {
  if (value === null || value === undefined) return 'n/a'
  return value ? 'yes' : 'no'
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'n/a'
  return value.replace('T', ' ').slice(0, 16)
}

function formatDateRange(start: string | null, end: string | null): string {
  if (!start && !end) return 'n/a'
  return `${formatDate(start)} to ${formatDate(end)}`
}
