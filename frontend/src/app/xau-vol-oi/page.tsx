'use client'

import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { api } from '@/services/api'
import {
  XauDashboardData,
  XauAcceptanceResult,
  XauExpectedRange,
  XauFreshnessResult,
  XauOiWall,
  XauOpenRegimeResult,
  XauReactionDashboardData,
  XauReactionReportSummary,
  XauReactionRow,
  XauRiskPlan,
  XauVolRegimeResult,
  XauVolOiReportSummary,
  XauZone,
} from '@/types'

export default function XauVolOiPage() {
  const [reports, setReports] = useState<XauVolOiReportSummary[]>([])
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [dashboardData, setDashboardData] = useState<XauDashboardData | null>(null)
  const [reactionReports, setReactionReports] = useState<XauReactionReportSummary[]>([])
  const [selectedReactionReportId, setSelectedReactionReportId] = useState<string | null>(null)
  const [reactionData, setReactionData] = useState<XauReactionDashboardData | null>(null)
  const [loadingReports, setLoadingReports] = useState(true)
  const [loadingReport, setLoadingReport] = useState(false)
  const [loadingReactionReports, setLoadingReactionReports] = useState(true)
  const [loadingReactionReport, setLoadingReactionReport] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reactionError, setReactionError] = useState<string | null>(null)

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
    let active = true
    setLoadingReactionReports(true)
    api.listXauReactionReports()
      .then((response) => {
        if (!active) return
        setReactionReports(response.reports)
      })
      .catch((err) => {
        if (!active) return
        setReactionError(
          err instanceof Error ? err.message : 'XAU reaction reports could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingReactionReports(false)
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

  useEffect(() => {
    if (reactionReports.length === 0) {
      setSelectedReactionReportId(null)
      return
    }

    setSelectedReactionReportId((current) => {
      const currentSummary = reactionReports.find((item) => item.report_id === current)
      if (
        current &&
        currentSummary &&
        (!selectedReportId || currentSummary.source_report_id === selectedReportId)
      ) {
        return current
      }
      const sourceMatch = reactionReports.find((item) => item.source_report_id === selectedReportId)
      return sourceMatch?.report_id ?? reactionReports[0].report_id
    })
  }, [reactionReports, selectedReportId])

  useEffect(() => {
    if (!selectedReactionReportId) {
      setReactionData(null)
      return
    }

    let active = true
    setLoadingReactionReport(true)
    setReactionError(null)
    api.getXauReactionDashboardData(selectedReactionReportId)
      .then((response) => {
        if (!active) return
        setReactionData(response)
      })
      .catch((err) => {
        if (!active) return
        setReactionData(null)
        setReactionError(
          err instanceof Error ? err.message : 'XAU reaction report could not be loaded',
        )
      })
      .finally(() => {
        if (active) setLoadingReactionReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedReactionReportId])

  const selectedSummary = useMemo(
    () => reports.find((item) => item.report_id === selectedReportId) ?? null,
    [reports, selectedReportId],
  )
  const selectedReactionSummary = useMemo(
    () => reactionReports.find((item) => item.report_id === selectedReactionReportId) ?? null,
    [reactionReports, selectedReactionReportId],
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
      <ReactionReportInspection
        reports={reactionReports}
        selectedReportId={selectedReactionReportId}
        selectedSummary={selectedReactionSummary}
        data={reactionData}
        loadingList={loadingReactionReports}
        loadingReport={loadingReactionReport}
        error={reactionError}
        onSelect={setSelectedReactionReportId}
      />

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
      XAU Vol-OI walls, zones, reactions, and bounded risk plans are research
      annotations only. They require source-data review, context review, and manual
      validation before any operational use.
    </Notice>
  )
}

function ReactionReportInspection({
  reports,
  selectedReportId,
  selectedSummary,
  data,
  loadingList,
  loadingReport,
  error,
  onSelect,
}: {
  reports: XauReactionReportSummary[]
  selectedReportId: string | null
  selectedSummary: XauReactionReportSummary | null
  data: XauReactionDashboardData | null
  loadingList: boolean
  loadingReport: boolean
  error: string | null
  onSelect: (reportId: string | null) => void
}) {
  const report = data?.report ?? null
  const reactions = data?.reactions.data ?? report?.reactions ?? []
  const riskPlans = data?.riskPlan.data ?? report?.risk_plans ?? []
  const acceptanceStates = reactions
    .map((reaction) => reaction.acceptance_state)
    .filter((state): state is XauAcceptanceResult => state !== null)
  const noTradeReasons = uniqueValues(reactions.flatMap((reaction) => reaction.no_trade_reasons))

  return (
    <ReportSection title="XAU Reaction Reports">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-gray-400">
            Saved reaction reports derived from feature 006 XAU Vol-OI reports.
          </p>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-300">
              Source report: {selectedSummary.source_report_id} | {selectedSummary.status} |{' '}
              {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Reaction report
          <select
            value={selectedReportId ?? ''}
            onChange={(event) => onSelect(event.target.value || null)}
            className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingList || reports.length === 0}
          >
            {reports.length === 0 ? (
              <option value="">No reaction reports</option>
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

      {error && <div className="mt-4"><Notice tone="error">{error}</Notice></div>}

      {loadingList ? (
        <div className="mt-4">
          <EmptyState>Loading XAU reaction reports...</EmptyState>
        </div>
      ) : reports.length === 0 ? (
        <div className="mt-4">
          <EmptyState>No saved XAU reaction reports are available.</EmptyState>
        </div>
      ) : loadingReport ? (
        <div className="mt-4">
          <EmptyState>Loading selected XAU reaction report...</EmptyState>
        </div>
      ) : report ? (
        <div className="mt-5 space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <SummaryCard label="Status" value={report.status} />
            <SummaryCard label="Source Walls" value={report.source_wall_count} />
            <SummaryCard label="Reactions" value={report.reaction_count} />
            <SummaryCard label="No-Trade" value={report.no_trade_count} />
            <SummaryCard label="Risk Plans" value={report.risk_plan_count} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="Freshness">
              <FreshnessPanel state={report.freshness_state} />
            </ContextPanel>
            <ContextPanel title="IV/RV/VRP">
              <VolRegimePanel state={report.vol_regime_state} />
            </ContextPanel>
            <ContextPanel title="Session Open">
              <OpenRegimePanel state={report.open_regime_state} />
            </ContextPanel>
          </div>

          <ContextPanel title="Acceptance / Rejection State">
            <AcceptanceStateList states={acceptanceStates} />
          </ContextPanel>

          <ContextPanel title="Reaction Labels">
            <ReactionTable rows={reactions} />
          </ContextPanel>

          <ContextPanel title="Bounded Risk Planner">
            <RiskPlanTable rows={riskPlans} />
          </ContextPanel>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            <ContextPanel title="No-Trade Reasons">
              <NotesList notes={noTradeReasons} emptyText="No no-trade reasons in this report" />
            </ContextPanel>
            <ContextPanel title="Warnings">
              <NotesList notes={report.warnings} emptyText="No warnings" />
            </ContextPanel>
            <ContextPanel title="Limitations">
              <NotesList notes={report.limitations} emptyText="No limitations" />
            </ContextPanel>
          </div>
        </div>
      ) : null}
    </ReportSection>
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

function ContextPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-gray-700 bg-gray-900 p-4">
      <h4 className="mb-3 text-sm font-semibold text-gray-100">{title}</h4>
      {children}
    </div>
  )
}

function FreshnessPanel({ state }: { state: XauFreshnessResult }) {
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="State" value={state.state} />
      <Metric label="Confidence" value={state.confidence_label} />
      <Metric label="Age Minutes" value={formatNumber(state.age_minutes)} />
      <Metric label="No-Trade Reason" value={state.no_trade_reason ?? 'n/a'} />
      {state.notes.length > 0 && (
        <div className="sm:col-span-2">
          <NotesList notes={state.notes} emptyText="No freshness notes" />
        </div>
      )}
    </dl>
  )
}

function VolRegimePanel({ state }: { state: XauVolRegimeResult }) {
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="Realized Vol" value={formatNumber(state.realized_volatility)} />
      <Metric label="VRP" value={formatNumber(state.vrp)} />
      <Metric label="VRP Regime" value={state.vrp_regime} />
      <Metric label="IV Edge" value={state.iv_edge_state} />
      <Metric label="RV Extension" value={state.rv_extension_state} />
      <Metric label="Confidence" value={state.confidence_label} />
      {state.notes.length > 0 && (
        <div className="sm:col-span-2">
          <NotesList notes={state.notes} emptyText="No volatility notes" />
        </div>
      )}
    </dl>
  )
}

function OpenRegimePanel({ state }: { state: XauOpenRegimeResult }) {
  return (
    <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
      <Metric label="Open Side" value={state.open_side} />
      <Metric label="Distance" value={formatNumber(state.open_distance_points)} />
      <Metric label="Flip State" value={state.open_flip_state} />
      <Metric label="Boundary" value={state.open_as_support_or_resistance} />
      <Metric label="Confidence" value={state.confidence_label} />
      {state.notes.length > 0 && (
        <div className="sm:col-span-2">
          <NotesList notes={state.notes} emptyText="No open-regime notes" />
        </div>
      )}
    </dl>
  )
}

function AcceptanceStateList({ states }: { states: XauAcceptanceResult[] }) {
  if (states.length === 0) {
    return <p className="text-sm text-gray-400">No candle acceptance state was recorded.</p>
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {states.map((state) => (
        <div key={`${state.wall_id ?? 'wall'}-${state.zone_id ?? 'zone'}`} className="text-sm">
          <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Metric label="Wall" value={state.wall_id ?? 'n/a'} />
            <Metric label="Zone" value={state.zone_id ?? 'n/a'} />
            <Metric label="Direction" value={state.direction} />
            <Metric label="Confidence" value={state.confidence_label} />
            <Metric label="Accepted" value={formatBoolean(state.accepted_beyond_wall)} />
            <Metric label="Confirmed" value={formatBoolean(state.confirmed_breakout)} />
            <Metric label="Wick Rejection" value={formatBoolean(state.wick_rejection)} />
            <Metric label="Failed Break" value={formatBoolean(state.failed_breakout)} />
          </dl>
          {state.notes.length > 0 && (
            <div className="mt-3">
              <NotesList notes={state.notes} emptyText="No acceptance notes" />
            </div>
          )}
        </div>
      ))}
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

function ReactionTable({ rows }: { rows: XauReactionRow[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No reaction rows were generated.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Reaction</th>
            <th className="px-3 py-2">Wall</th>
            <th className="px-3 py-2">Zone</th>
            <th className="px-3 py-2">Label</th>
            <th className="px-3 py-2">Confidence</th>
            <th className="px-3 py-2">Invalidation</th>
            <th className="px-3 py-2">Target 1</th>
            <th className="px-3 py-2">Target 2</th>
            <th className="px-3 py-2">Next Wall</th>
            <th className="px-3 py-2">Notes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.reaction_id} className="border-t border-gray-700 align-top">
              <td className="px-3 py-2">{row.reaction_id}</td>
              <td className="px-3 py-2">{row.wall_id ?? 'n/a'}</td>
              <td className="px-3 py-2">{row.zone_id ?? 'n/a'}</td>
              <td className="px-3 py-2">{row.reaction_label}</td>
              <td className="px-3 py-2">{row.confidence_label}</td>
              <td className="px-3 py-2">{formatNumber(row.invalidation_level)}</td>
              <td className="px-3 py-2">{formatNumber(row.target_level_1)}</td>
              <td className="px-3 py-2">{formatNumber(row.target_level_2)}</td>
              <td className="px-3 py-2">{row.next_wall_reference ?? 'n/a'}</td>
              <td className="max-w-md px-3 py-2 text-gray-300">
                {row.explanation_notes.join(' ')}
                {row.no_trade_reasons.length > 0 && (
                  <div className="mt-2 text-amber-200">
                    {row.no_trade_reasons.join(' ')}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RiskPlanTable({ rows }: { rows: XauRiskPlan[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No bounded risk-plan rows were generated.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Plan</th>
            <th className="px-3 py-2">Reaction</th>
            <th className="px-3 py-2">Label</th>
            <th className="px-3 py-2">Condition</th>
            <th className="px-3 py-2">Invalidation</th>
            <th className="px-3 py-2">Buffer</th>
            <th className="px-3 py-2">Target 1</th>
            <th className="px-3 py-2">Target 2</th>
            <th className="px-3 py-2">Recovery</th>
            <th className="px-3 py-2">RR State</th>
            <th className="px-3 py-2">Cancel Conditions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.plan_id} className="border-t border-gray-700 align-top">
              <td className="px-3 py-2">{row.plan_id}</td>
              <td className="px-3 py-2">{row.reaction_id}</td>
              <td className="px-3 py-2">{row.reaction_label}</td>
              <td className="max-w-sm px-3 py-2 text-gray-300">
                {row.entry_condition_text ?? 'n/a'}
              </td>
              <td className="px-3 py-2">{formatNumber(row.invalidation_level)}</td>
              <td className="px-3 py-2">{formatNumber(row.stop_buffer_points)}</td>
              <td className="px-3 py-2">{formatNumber(row.target_1)}</td>
              <td className="px-3 py-2">{formatNumber(row.target_2)}</td>
              <td className="px-3 py-2">{row.max_recovery_legs}</td>
              <td className="px-3 py-2">{row.rr_state}</td>
              <td className="max-w-md px-3 py-2 text-gray-300">
                {[...row.cancel_conditions, ...row.risk_notes].join(' ')}
              </td>
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

function formatBoolean(value: boolean): string {
  return value ? 'yes' : 'no'
}

function formatPercent(value: number): string {
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`
}
