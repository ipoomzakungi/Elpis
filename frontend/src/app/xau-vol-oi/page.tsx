'use client'

import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { api } from '@/services/api'
import {
  XauDashboardData,
  XauExpectedRange,
  XauOiWall,
  XauVolOiReportSummary,
  XauZone,
} from '@/types'

export default function XauVolOiPage() {
  const [reports, setReports] = useState<XauVolOiReportSummary[]>([])
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [dashboardData, setDashboardData] = useState<XauDashboardData | null>(null)
  const [loadingReports, setLoadingReports] = useState(true)
  const [loadingReport, setLoadingReport] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoadingReports(true)
    api.getXauVolOiReports()
      .then((response) => {
        if (!active) return
        setReports(response.reports)
        setSelectedReportId((current) => current ?? response.reports[0]?.report_id ?? null)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'XAU reports could not be loaded')
      })
      .finally(() => {
        if (active) setLoadingReports(false)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedReportId) {
      setDashboardData(null)
      return
    }

    let active = true
    setLoadingReport(true)
    setError(null)
    api.getXauVolOiDashboardData(selectedReportId)
      .then((response) => {
        if (!active) return
        setDashboardData(response)
      })
      .catch((err) => {
        if (!active) return
        setDashboardData(null)
        setError(err instanceof Error ? err.message : 'XAU report could not be loaded')
      })
      .finally(() => {
        if (active) setLoadingReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedReportId])

  const selectedSummary = useMemo(
    () => reports.find((item) => item.report_id === selectedReportId) ?? null,
    [reports, selectedReportId],
  )

  const report = dashboardData?.report ?? null
  const warningNotes = uniqueValues([
    ...(report?.warnings ?? []),
    ...(report?.source_validation.warnings ?? []),
  ])
  const limitationNotes = uniqueValues([
    ...(report?.limitations ?? []),
    ...(report?.walls.flatMap((wall) => wall.limitations) ?? []),
    ...(report?.zones.flatMap((zone) => zone.limitations) ?? []),
  ])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-amber-300">Research report</p>
          <h2 className="mt-1 text-xl font-semibold">XAU Vol-OI Walls</h2>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-400">
              {selectedSummary.report_id} | {selectedSummary.status} |{' '}
              {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Report
          <select
            value={selectedReportId ?? ''}
            onChange={(event) => setSelectedReportId(event.target.value || null)}
            className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingReports || reports.length === 0}
          >
            {reports.length === 0 ? (
              <option value="">No XAU reports</option>
            ) : (
              reports.map((item) => (
                <option key={item.report_id} value={item.report_id}>
                  {item.report_id}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      <ResearchOnlyNotice />

      {error && <Notice tone="error">{error}</Notice>}

      {loadingReports ? (
        <EmptyState>Loading XAU Vol-OI reports...</EmptyState>
      ) : reports.length === 0 ? (
        <EmptyState>No XAU Vol-OI reports are available.</EmptyState>
      ) : loadingReport ? (
        <EmptyState>Loading XAU Vol-OI report...</EmptyState>
      ) : report ? (
        <>
          <StatusSummary report={report} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ReportSection title="Basis Snapshot">
              <BasisSnapshot data={report.basis_snapshot} />
            </ReportSection>
            <ReportSection title="Expected Range">
              <ExpectedRangeCard range={report.expected_range} />
            </ReportSection>
          </div>

          {(report.missing_data_instructions.length > 0 ||
            warningNotes.length > 0 ||
            limitationNotes.length > 0) && (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
              <ReportSection title="Missing Data">
                <NotesList
                  notes={report.missing_data_instructions}
                  emptyText="No missing-data instructions"
                />
              </ReportSection>
              <ReportSection title="Warnings">
                <NotesList notes={warningNotes} emptyText="No warnings" />
              </ReportSection>
              <ReportSection title="Limitations">
                <NotesList notes={limitationNotes} emptyText="No limitations" />
              </ReportSection>
            </div>
          )}

          <ReportSection title="Basis-Adjusted OI Walls">
            <WallTable rows={dashboardData?.walls.data ?? report.walls} />
          </ReportSection>

          <ReportSection title="Zone Classification">
            <ZoneTable rows={dashboardData?.zones.data ?? report.zones} />
          </ReportSection>
        </>
      ) : null}
    </div>
  )
}

function ResearchOnlyNotice() {
  return (
    <Notice tone="warning">
      XAU Vol-OI walls and zones are research annotations only. They are not buy/sell
      signals, profitability evidence, predictive proof, safety evidence, or
      live-readiness evidence.
    </Notice>
  )
}

function StatusSummary({ report }: { report: NonNullable<XauDashboardData['report']> }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <SummaryCard label="Status" value={report.status} />
      <SummaryCard label="Source Rows" value={report.source_row_count} />
      <SummaryCard label="Accepted" value={report.accepted_row_count} />
      <SummaryCard label="Walls" value={report.wall_count} />
      <SummaryCard label="Zones" value={report.zone_count} />
    </div>
  )
}

function SummaryCard({ label, value }: { label: number | string; value: number | string }) {
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

function BasisSnapshot({ data }: { data: XauDashboardData['report']['basis_snapshot'] }) {
  if (!data) {
    return <p className="text-sm text-gray-400">Basis snapshot unavailable.</p>
  }
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="Basis" value={formatNumber(data.basis)} />
      <Metric label="Source" value={data.basis_source} />
      <Metric label="Mapping" value={data.mapping_available ? 'available' : 'unavailable'} />
      <Metric label="Alignment" value={data.timestamp_alignment_status} />
      <Metric label="Spot" value={data.spot_reference?.symbol ?? 'n/a'} />
      <Metric label="Futures" value={data.futures_reference?.symbol ?? 'n/a'} />
      {data.notes.length > 0 && (
        <div className="sm:col-span-2">
          <NotesList notes={data.notes} emptyText="No basis notes" />
        </div>
      )}
    </dl>
  )
}

function ExpectedRangeCard({ range }: { range: XauExpectedRange | null }) {
  if (!range) {
    return <p className="text-sm text-gray-400">Expected range unavailable.</p>
  }
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="Source" value={range.source} />
      <Metric label="Reference" value={formatNumber(range.reference_price)} />
      <Metric label="Expected Move" value={formatNumber(range.expected_move)} />
      <Metric label="Days" value={range.days_to_expiry ?? 'n/a'} />
      <Metric label="Lower 1SD" value={formatNumber(range.lower_1sd)} />
      <Metric label="Upper 1SD" value={formatNumber(range.upper_1sd)} />
      <Metric label="Lower 2SD" value={formatNumber(range.lower_2sd)} />
      <Metric label="Upper 2SD" value={formatNumber(range.upper_2sd)} />
      {range.unavailable_reason && (
        <div className="sm:col-span-2 text-amber-200">{range.unavailable_reason}</div>
      )}
    </dl>
  )
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <dt className="text-xs uppercase text-gray-400">{label}</dt>
      <dd className="mt-1 text-white">{value}</dd>
    </div>
  )
}

function WallTable({ rows }: { rows: XauOiWall[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No wall rows were generated.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Expiry</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Strike</th>
            <th className="px-3 py-2">Spot Eq.</th>
            <th className="px-3 py-2">OI</th>
            <th className="px-3 py-2">OI Share</th>
            <th className="px-3 py-2">Expiry Weight</th>
            <th className="px-3 py-2">Freshness</th>
            <th className="px-3 py-2">Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.wall_id} className="border-t border-gray-700">
              <td className="px-3 py-2">{row.expiry}</td>
              <td className="px-3 py-2">{row.option_type}</td>
              <td className="px-3 py-2">{formatNumber(row.strike)}</td>
              <td className="px-3 py-2">{formatNumber(row.spot_equivalent_level)}</td>
              <td className="px-3 py-2">{formatNumber(row.open_interest)}</td>
              <td className="px-3 py-2">{formatPercent(row.oi_share)}</td>
              <td className="px-3 py-2">{formatNumber(row.expiry_weight)}</td>
              <td className="px-3 py-2">{row.freshness_status}</td>
              <td className="px-3 py-2">{formatNumber(row.wall_score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ZoneTable({ rows }: { rows: XauZone[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No zone rows were generated.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Zone</th>
            <th className="px-3 py-2">Level</th>
            <th className="px-3 py-2">Bounds</th>
            <th className="px-3 py-2">Wall Score</th>
            <th className="px-3 py-2">Pin</th>
            <th className="px-3 py-2">Squeeze</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">No-trade</th>
            <th className="px-3 py-2">Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.zone_id} className="border-t border-gray-700 align-top">
              <td className="px-3 py-2">{row.zone_type}</td>
              <td className="px-3 py-2">{formatNumber(row.level)}</td>
              <td className="px-3 py-2">
                {formatNumber(row.lower_bound)} / {formatNumber(row.upper_bound)}
              </td>
              <td className="px-3 py-2">{formatNumber(row.wall_score)}</td>
              <td className="px-3 py-2">{formatNumber(row.pin_risk_score)}</td>
              <td className="px-3 py-2">{formatNumber(row.squeeze_risk_score)}</td>
              <td className="px-3 py-2">{row.confidence}</td>
              <td className="px-3 py-2">{row.no_trade_warning ? 'yes' : 'no'}</td>
              <td className="max-w-md px-3 py-2 text-gray-300">{row.notes.join(' ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function NotesList({ notes, emptyText }: { notes: string[]; emptyText: string }) {
  if (notes.length === 0) {
    return <p className="text-sm text-gray-400">{emptyText}</p>
  }
  return (
    <ul className="space-y-2 text-sm text-gray-300">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  )
}

function uniqueValues(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)))
}

function formatDate(value: string | null): string {
  if (!value) return 'n/a'
  return new Date(value).toLocaleString()
}

function formatNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) return 'n/a'
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function formatPercent(value: number): string {
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`
}
