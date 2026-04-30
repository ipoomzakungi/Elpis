'use client'

import { type ReactNode, useEffect, useMemo, useState } from 'react'
import DrawdownChart from '@/components/charts/DrawdownChart'
import EquityCurveChart from '@/components/charts/EquityCurveChart'
import BacktestSummaryCards from '@/components/panels/BacktestSummaryCards'
import { api } from '@/services/api'
import {
  BacktestEquityPoint,
  BacktestMetricsResponse,
  BacktestRun,
  BacktestRunSummary,
  BacktestTrade,
  ParameterSensitivityResult,
  RegimeCoverageReport,
  StressResult,
  TradeConcentrationReport,
  ValidationRunSummary,
  WalkForwardResult,
} from '@/types'

const TRADE_LIMIT = 200

export default function BacktestsPage() {
  const [runs, setRuns] = useState<BacktestRunSummary[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [run, setRun] = useState<BacktestRun | null>(null)
  const [metrics, setMetrics] = useState<BacktestMetricsResponse | null>(null)
  const [trades, setTrades] = useState<BacktestTrade[]>([])
  const [equity, setEquity] = useState<BacktestEquityPoint[]>([])
  const [validationRuns, setValidationRuns] = useState<ValidationRunSummary[]>([])
  const [selectedValidationRunId, setSelectedValidationRunId] = useState<string | null>(null)
  const [stressResults, setStressResults] = useState<StressResult[]>([])
  const [sensitivityResults, setSensitivityResults] = useState<ParameterSensitivityResult[]>([])
  const [walkForwardResults, setWalkForwardResults] = useState<WalkForwardResult[]>([])
  const [regimeCoverage, setRegimeCoverage] = useState<RegimeCoverageReport | null>(null)
  const [concentrationReport, setConcentrationReport] = useState<TradeConcentrationReport | null>(null)
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [loadingReport, setLoadingReport] = useState(false)
  const [loadingValidation, setLoadingValidation] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoadingRuns(true)
    api.getBacktests()
      .then((response) => {
        if (!active) return
        setRuns(response.runs)
        setSelectedRunId((current) => current ?? response.runs[0]?.run_id ?? null)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Backtest runs could not be loaded')
      })
      .finally(() => {
        if (active) setLoadingRuns(false)
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    api.getValidationReports()
      .then((response) => {
        if (!active) return
        setValidationRuns(response.runs)
        setSelectedValidationRunId((current) => current ?? response.runs[0]?.validation_run_id ?? null)
      })
      .catch(() => {
        if (!active) return
        setValidationRuns([])
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedRunId) {
      setRun(null)
      setMetrics(null)
      setTrades([])
      setEquity([])
      return
    }

    let active = true
    setLoadingReport(true)
    setError(null)
    Promise.all([
      api.getBacktestRun(selectedRunId),
      api.getBacktestTrades(selectedRunId, { limit: TRADE_LIMIT, offset: 0 }),
      api.getBacktestMetrics(selectedRunId),
      api.getBacktestEquity(selectedRunId),
    ])
      .then(([runResponse, tradeResponse, metricsResponse, equityResponse]) => {
        if (!active) return
        setRun(runResponse)
        setTrades(tradeResponse.data)
        setMetrics(metricsResponse)
        setEquity(equityResponse.data)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Backtest report could not be loaded')
      })
      .finally(() => {
        if (active) setLoadingReport(false)
      })

    return () => {
      active = false
    }
  }, [selectedRunId])

  useEffect(() => {
    if (!selectedValidationRunId) {
      setStressResults([])
      setSensitivityResults([])
      setWalkForwardResults([])
      setRegimeCoverage(null)
      setConcentrationReport(null)
      return
    }

    let active = true
    setLoadingValidation(true)
    Promise.all([
      api.getValidationStress(selectedValidationRunId),
      api.getValidationSensitivity(selectedValidationRunId),
      api.getValidationWalkForward(selectedValidationRunId),
      api.getValidationConcentration(selectedValidationRunId),
    ])
      .then(([stressResponse, sensitivityResponse, walkForwardResponse, concentrationResponse]) => {
        if (!active) return
        setStressResults(stressResponse.data)
        setSensitivityResults(sensitivityResponse.data)
        setWalkForwardResults(walkForwardResponse.data)
        setRegimeCoverage(concentrationResponse.regime_coverage)
        setConcentrationReport(concentrationResponse.concentration_report)
      })
      .catch(() => {
        if (!active) return
        setStressResults([])
        setSensitivityResults([])
        setWalkForwardResults([])
        setRegimeCoverage(null)
        setConcentrationReport(null)
      })
      .finally(() => {
        if (active) setLoadingValidation(false)
      })

    return () => {
      active = false
    }
  }, [selectedValidationRunId])

  const selectedSummary = useMemo(
    () => runs.find((item) => item.run_id === selectedRunId) ?? null,
    [runs, selectedRunId],
  )

  const notes = useMemo(() => {
    const values = [
      'Historical simulation outputs only; not profitability evidence, predictive proof, safety evidence, or live-trading readiness.',
      ...(run?.warnings ?? []),
      ...(run?.limitations ?? []),
      ...(metrics?.notes ?? []),
    ]
    return Array.from(new Set(values))
  }, [run?.warnings, run?.limitations, metrics?.notes])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-xl font-semibold">Backtest Reports</h2>
          {selectedSummary && (
            <p className="mt-2 text-sm text-gray-400">
              {selectedSummary.symbol} {selectedSummary.timeframe} | {selectedSummary.status} | {formatDate(selectedSummary.created_at)}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Run
          <select
            value={selectedRunId ?? ''}
            onChange={(event) => setSelectedRunId(event.target.value || null)}
            className="min-w-72 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            disabled={loadingRuns || runs.length === 0}
          >
            {runs.length === 0 ? (
              <option value="">No runs</option>
            ) : (
              runs.map((item) => (
                <option key={item.run_id} value={item.run_id}>
                  {item.run_id}
                </option>
              ))
            )}
          </select>
        </label>
      </div>

      {error && <div className="rounded-md border border-red-900 bg-red-950 px-4 py-3 text-sm text-red-200">{error}</div>}

      {loadingRuns ? (
        <div className="rounded-md bg-gray-800 p-4 text-sm text-gray-400">Loading runs...</div>
      ) : runs.length === 0 ? (
        <div className="rounded-md bg-gray-800 p-4 text-sm text-gray-400">No completed backtest runs are available.</div>
      ) : (
        <>
          <BacktestSummaryCards metrics={metrics?.summary} />

          {loadingReport ? (
            <div className="rounded-md bg-gray-800 p-4 text-sm text-gray-400">Loading report...</div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                <ReportSection title="Equity Curve">
                  <EquityCurveChart data={equity} height={300} />
                </ReportSection>
                <ReportSection title="Drawdown">
                  <DrawdownChart data={equity} height={300} />
                </ReportSection>
              </div>

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                <ReportSection title="Assumptions">
                  <KeyValueTable
                    rows={objectRows({
                      ...run?.config.assumptions,
                      initial_equity: run?.config.initial_equity,
                      config_hash: run?.config_hash,
                    })}
                  />
                </ReportSection>
                <ReportSection title="Data Identity">
                  <KeyValueTable rows={objectRows(run?.data_identity ?? {})} />
                </ReportSection>
              </div>

              <ReportSection title="Trades">
                <TradeTable trades={trades} />
              </ReportSection>

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                <ReportSection title="Regime Performance">
                  <MetricTable
                    rows={metrics?.return_by_regime ?? []}
                    columns={[
                      { key: 'regime', label: 'Regime' },
                      { key: 'number_of_trades', label: 'Trades' },
                      { key: 'return_pct_display', label: 'Return %', format: formatNumber },
                      { key: 'win_rate', label: 'Win Rate', format: formatRatioPercent },
                    ]}
                  />
                </ReportSection>
                <ReportSection title="Strategy Modes">
                  <MetricTable
                    rows={metrics?.return_by_strategy_mode ?? []}
                    columns={[
                      { key: 'strategy_mode', label: 'Mode' },
                      { key: 'category', label: 'Category' },
                      { key: 'number_of_trades', label: 'Trades' },
                      { key: 'total_return_pct', label: 'Total Return %', format: formatNumber },
                      { key: 'max_drawdown_pct', label: 'Max Drawdown %', format: formatNumber },
                      { key: 'equity_basis', label: 'Equity Basis' },
                    ]}
                  />
                </ReportSection>
              </div>

              <ReportSection title="Baseline Comparison">
                <MetricTable
                  rows={metrics?.baseline_comparison ?? []}
                  columns={[
                    { key: 'strategy_mode', label: 'Mode' },
                    { key: 'category', label: 'Category' },
                    { key: 'number_of_trades', label: 'Trades' },
                    { key: 'total_return_pct', label: 'Total Return %', format: formatNumber },
                    { key: 'max_drawdown_pct', label: 'Max Drawdown %', format: formatNumber },
                  ]}
                />
              </ReportSection>

              <ReportSection title="Validation Robustness">
                <div className="mb-4 flex flex-col gap-2 text-sm text-gray-300 md:w-96">
                  Validation run
                  <select
                    value={selectedValidationRunId ?? ''}
                    onChange={(event) => setSelectedValidationRunId(event.target.value || null)}
                    className="rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
                    disabled={validationRuns.length === 0}
                  >
                    {validationRuns.length === 0 ? (
                      <option value="">No validation runs</option>
                    ) : (
                      validationRuns.map((item) => (
                        <option key={item.validation_run_id} value={item.validation_run_id}>
                          {item.validation_run_id}
                        </option>
                      ))
                    )}
                  </select>
                </div>
                {loadingValidation ? (
                  <p className="text-sm text-gray-400">Loading validation tables...</p>
                ) : (
                  <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
                    <MetricTable
                      rows={stressRows(stressResults)}
                      columns={[
                        { key: 'profile', label: 'Profile' },
                        { key: 'mode', label: 'Mode' },
                        { key: 'category', label: 'Category' },
                        { key: 'outcome', label: 'Outcome' },
                        { key: 'total_return_pct', label: 'Total Return %', format: formatNumber },
                        { key: 'trades', label: 'Trades' },
                        { key: 'fee_rate', label: 'Fee', format: formatRate },
                        { key: 'slippage_rate', label: 'Slippage', format: formatRate },
                      ]}
                    />
                    <MetricTable
                      rows={sensitivityRows(sensitivityResults)}
                      columns={[
                        { key: 'parameter_set_id', label: 'Parameter Set' },
                        { key: 'mode', label: 'Mode' },
                        { key: 'profile', label: 'Cost' },
                        { key: 'entry_threshold', label: 'Entry', format: formatNumber },
                        { key: 'atr_stop_buffer', label: 'ATR', format: formatNumber },
                        { key: 'risk_reward', label: 'R Multiple', format: formatNumber },
                        { key: 'total_return_pct', label: 'Total Return %', format: formatNumber },
                        { key: 'fragility_flag', label: 'Fragile' },
                      ]}
                    />
                    <MetricTable
                      rows={walkForwardRows(walkForwardResults)}
                      columns={[
                        { key: 'split_id', label: 'Split' },
                        { key: 'start', label: 'Start' },
                        { key: 'end', label: 'End' },
                        { key: 'row_count', label: 'Rows' },
                        { key: 'trade_count', label: 'Trades' },
                        { key: 'status', label: 'Status' },
                        { key: 'notes', label: 'Notes' },
                      ]}
                    />
                    <MetricTable
                      rows={regimeCoverageRows(regimeCoverage)}
                      columns={[
                        { key: 'regime', label: 'Regime' },
                        { key: 'bars', label: 'Bars' },
                        { key: 'trades', label: 'Trades' },
                        { key: 'net_pnl', label: 'Net PnL', format: formatNumber },
                        { key: 'return_pct', label: 'Return %', format: formatNumber },
                      ]}
                    />
                    <MetricTable
                      rows={concentrationRows(concentrationReport)}
                      columns={[
                        { key: 'metric', label: 'Metric' },
                        { key: 'value', label: 'Value' },
                      ]}
                    />
                  </div>
                )}
              </ReportSection>

              {concentrationReport && (
                <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                  <ReportSection title="Best Trades">
                    <TradeTable trades={concentrationReport.best_trades} />
                  </ReportSection>
                  <ReportSection title="Worst Trades">
                    <TradeTable trades={concentrationReport.worst_trades} />
                  </ReportSection>
                </div>
              )}

              {regimeCoverage?.coverage_notes.length || concentrationReport?.notes.length ? (
                <div className="rounded-md border border-yellow-900 bg-yellow-950 p-4 text-sm text-yellow-100">
                  {[...(regimeCoverage?.coverage_notes ?? []), ...(concentrationReport?.notes ?? [])].map((note) => (
                    <p key={note}>{note}</p>
                  ))}
                </div>
              ) : null}

              {notes.length > 0 && (
                <div className="rounded-md border border-amber-900 bg-amber-950 p-4 text-sm text-amber-100">
                  {notes.map((note) => (
                    <p key={note}>{note}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
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

function TradeTable({ trades }: { trades: BacktestTrade[] }) {
  if (trades.length === 0) {
    return <p className="text-sm text-gray-400">No trades</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Trade</th>
            <th className="px-3 py-2">Mode</th>
            <th className="px-3 py-2">Side</th>
            <th className="px-3 py-2">Regime</th>
            <th className="px-3 py-2">Entry</th>
            <th className="px-3 py-2">Exit</th>
            <th className="px-3 py-2">Net PnL</th>
            <th className="px-3 py-2">Fees</th>
            <th className="px-3 py-2">Slippage</th>
            <th className="px-3 py-2">Bars</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {trades.map((trade) => (
            <tr key={trade.trade_id}>
              <td className="px-3 py-2 text-gray-300">{trade.trade_id}</td>
              <td className="px-3 py-2">{trade.strategy_mode}</td>
              <td className="px-3 py-2">{trade.side}</td>
              <td className="px-3 py-2">{trade.regime_at_signal ?? 'n/a'}</td>
              <td className="px-3 py-2">{formatDate(trade.entry_timestamp)}</td>
              <td className="px-3 py-2">{formatDate(trade.exit_timestamp)}</td>
              <td className="px-3 py-2">{formatNumber(trade.net_pnl)}</td>
              <td className="px-3 py-2">{formatNumber(trade.fees)}</td>
              <td className="px-3 py-2">{formatNumber(trade.slippage)}</td>
              <td className="px-3 py-2">{trade.holding_bars}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface MetricColumn {
  key: string
  label: string
  format?: (value: unknown) => string
}

function MetricTable({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: MetricColumn[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No rows</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="px-3 py-2">{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {rows.map((row, index) => (
            <tr key={String(row[columns[0].key] ?? index)}>
              {columns.map((column) => (
                <td key={column.key} className="px-3 py-2">
                  {column.format ? column.format(row[column.key]) : formatValue(row[column.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function KeyValueTable({ rows }: { rows: Array<{ key: string; value: unknown }> }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400">No details</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <tbody className="divide-y divide-gray-700">
          {rows.map((row) => (
            <tr key={row.key}>
              <th className="w-44 px-3 py-2 text-xs uppercase text-gray-400">{row.key}</th>
              <td className="px-3 py-2 text-gray-200">{formatValue(row.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function objectRows(value: Record<string, unknown>): Array<{ key: string; value: unknown }> {
  return Object.entries(value).map(([key, item]) => ({ key, value: item }))
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'n/a'
  if (typeof value === 'number') return formatNumber(value)
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatNumber(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'n/a'
  return value.toFixed(2)
}

function formatRate(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'n/a'
  return `${(value * 100).toFixed(4)}%`
}

function formatRatioPercent(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'n/a'
  return `${(value * 100).toFixed(2)}%`
}

function formatDate(value: string): string {
  return value.replace('T', ' ').slice(0, 16)
}

function stressRows(results: StressResult[]): Array<Record<string, unknown>> {
  return results.map((row) => ({
    profile: row.profile.name,
    mode: row.strategy_mode,
    category: row.category,
    outcome: row.outcome,
    total_return_pct: row.metrics.total_return_pct,
    trades: row.metrics.number_of_trades,
    fee_rate: row.profile.fee_rate,
    slippage_rate: row.profile.slippage_rate,
  }))
}

function sensitivityRows(results: ParameterSensitivityResult[]): Array<Record<string, unknown>> {
  return results.map((row) => ({
    parameter_set_id: row.parameter_set_id,
    mode: row.strategy_mode,
    profile: row.stress_profile_name,
    entry_threshold: row.grid_entry_threshold,
    atr_stop_buffer: row.atr_stop_buffer,
    risk_reward: row.breakout_risk_reward_multiple,
    total_return_pct: row.metrics.total_return_pct,
    fragility_flag: row.fragility_flag ? 'yes' : 'no',
  }))
}

function walkForwardRows(results: WalkForwardResult[]): Array<Record<string, unknown>> {
  return results.map((row) => ({
    split_id: row.split_id,
    start: formatDate(row.start_timestamp),
    end: formatDate(row.end_timestamp),
    row_count: row.row_count,
    trade_count: row.trade_count,
    status: row.status,
    notes: row.notes.join(' '),
  }))
}

function regimeCoverageRows(report: RegimeCoverageReport | null): Array<Record<string, unknown>> {
  if (!report) return []
  return Object.entries(report.bar_counts).map(([regime, bars]) => {
    const summary = report.return_by_regime[regime] ?? {}
    return {
      regime,
      bars,
      trades: report.trades_per_regime[regime] ?? 0,
      net_pnl: summary.net_pnl ?? null,
      return_pct: summary.return_pct_display ?? null,
    }
  })
}

function concentrationRows(report: TradeConcentrationReport | null): Array<Record<string, unknown>> {
  if (!report) return []
  return [
    { metric: 'Top 1 Profit Contribution %', value: formatNumber(report.top_1_profit_contribution_pct) },
    { metric: 'Top 5 Profit Contribution %', value: formatNumber(report.top_5_profit_contribution_pct) },
    { metric: 'Top 10 Profit Contribution %', value: formatNumber(report.top_10_profit_contribution_pct) },
    { metric: 'Max Consecutive Losses', value: report.max_consecutive_losses },
    { metric: 'Drawdown Recovery Status', value: report.drawdown_recovery_status },
    {
      metric: 'Drawdown Recovery Bars',
      value: report.drawdown_recovery_bars ?? 'n/a',
    },
  ]
}
