'use client'

import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { api } from '@/services/api'
import {
  XauPlanTrackerOrder,
  XauPlanTrackerOrderStatus,
  XauPlanTrackerRunResult,
  XauPlanTrackerSnapshot,
} from '@/types'

interface DashboardBundle {
  run: XauPlanTrackerRunResult
  snapshots: XauPlanTrackerSnapshot[]
  orders: XauPlanTrackerOrder[]
}

export default function XauPlanTrackerPage() {
  const [run, setRun] = useState<XauPlanTrackerRunResult | null>(null)
  const [snapshots, setSnapshots] = useState<XauPlanTrackerSnapshot[]>([])
  const [orders, setOrders] = useState<XauPlanTrackerOrder[]>([])
  const [runIdInput, setRunIdInput] = useState('')
  const [loadingLatest, setLoadingLatest] = useState(true)
  const [loadingRun, setLoadingRun] = useState(false)
  const [notReadyMessage, setNotReadyMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadRunBundle = async (runId: string): Promise<DashboardBundle> => {
    const [runData, runSnapshots, runOrders] = await Promise.all([
      api.getXauPlanTrackerRun(runId),
      api.getXauPlanTrackerSnapshots(runId),
      api.getXauPlanTrackerOrders(runId),
    ])
    return { run: runData, snapshots: runSnapshots, orders: runOrders }
  }

  const setBundle = ({ run: nextRun, snapshots: nextSnapshots, orders: nextOrders }: DashboardBundle) => {
    setRun(nextRun)
    setSnapshots(
      [...nextSnapshots].sort(
        (a, b) => new Date(a.planning_time).getTime() - new Date(b.planning_time).getTime(),
      ),
    )
    setOrders(nextOrders)
  }

  useEffect(() => {
    let mounted = true
    setLoadingLatest(true)
    setNotReadyMessage(null)
    setError(null)

    api
      .getLatestXauPlanTrackerRun()
      .then(async (latestRun) => {
        if (!mounted) return
        setRunIdInput(latestRun.run_id)
        setLoadingRun(true)
        setBundle(await loadRunBundle(latestRun.run_id))
        setLoadingRun(false)
      })
      .catch((err) => {
        if (!mounted) return
        setNotReadyMessage(
          err instanceof Error
            ? err.message
            : 'No plan tracker run exists yet. Run backend/scripts/run_xau_plan_tracker.py first.',
        )
        setRun(null)
        setSnapshots([])
        setOrders([])
      })
      .finally(() => {
        if (mounted) {
          setLoadingLatest(false)
          setLoadingRun(false)
        }
      })

    return () => {
      mounted = false
    }
  }, [])

  const snapshotCards = useMemo(
    () => snapshots.map((snapshot) => ({ snapshot, id: `${snapshot.snapshot_id}-${snapshot.planning_time}` })),
    [snapshots],
  )

  const nearMissOrders = useMemo(() => orders.filter((order) => order.near_miss), [orders])
  const recoveryTriggeredOrders = useMemo(
    () => orders.filter((order) => order.status === 'recovery_triggered'),
    [orders],
  )
  const recoveryTargetOrders = useMemo(
    () => orders.filter((order) => order.status === 'recovery_target_hit'),
    [orders],
  )
  const openOrders = useMemo(() => orders.filter((order) => order.status === 'open'), [orders])
  const completedOrders = useMemo(
    () =>
      orders.filter((order) =>
        ['target_hit', 'stop_hit', 'recovery_target_hit', 'recovery_triggered'].includes(
          order.status,
        ),
      ),
    [orders],
  )

  const hasActiveRecovery = run
    ? recoveryTriggeredOrders.length > 0 || recoveryTargetOrders.length > 0
    : false

  const loadRunById = async () => {
    const requestedRunId = runIdInput.trim()
    if (!requestedRunId) return
    setError(null)
    setNotReadyMessage(null)
    setLoadingRun(true)
    try {
      setBundle(await loadRunBundle(requestedRunId))
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'The requested run could not be loaded. Confirm run_id and that it exists.',
      )
      setRun(null)
      setSnapshots([])
      setOrders([])
    } finally {
      setLoadingRun(false)
    }
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-amber-300">Research dashboard</p>
          <h2 className="mt-1 text-xl font-semibold">XAU Plan Tracker</h2>
          <p className="mt-2 max-w-3xl text-sm text-gray-400">
            Feature 026 plan snapshots and simulated outcomes for 10:10/18:10 trading windows.
          </p>
        </div>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          Run ID
          <div className="flex gap-2">
            <input
              value={runIdInput}
              onChange={(event) => setRunIdInput(event.target.value)}
              placeholder="xau_plan_tracker_2026-06-08_...."
              className="min-w-80 rounded-md border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            />
            <button
              type="button"
              onClick={loadRunById}
              disabled={!runIdInput.trim() || loadingRun}
              className="rounded-md bg-sky-300 px-3 py-2 text-sm font-medium text-zinc-950 transition hover:bg-sky-200 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
            >
              Load run
            </button>
          </div>
        </label>
      </section>

      <Notice tone="warning">Research simulation only. No live orders or broker actions are triggered.</Notice>

      {(error || notReadyMessage) && <Notice tone="error">{error ?? notReadyMessage}</Notice>}

      {loadingLatest ? (
        <EmptyState>Loading XAU plan tracker data...</EmptyState>
      ) : !run ? (
        <EmptyState>
          No plan-tracker run loaded.
          <span className="block text-sm text-gray-500">
            Run backend script first: backend/scripts/run_xau_plan_tracker.py
          </span>
        </EmptyState>
      ) : (
        <>
          <RunSummary run={run} />

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            {snapshotCards.map((item) => (
              <PlanSnapshotCard key={item.id} snapshot={item.snapshot} />
            ))}
          </div>

          <Panel title="Orders">
            {loadingRun ? (
              <EmptyState>Loading order details...</EmptyState>
            ) : orders.length === 0 ? (
              <EmptyState>No tracked orders were available for this run.</EmptyState>
            ) : (
              <OrdersTable orders={orders} />
            )}
          </Panel>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <Panel title="Recovery">
              <Metric label="Recovery enabled" value={run.readiness === 'complete' ? 'ready' : run.readiness} />
              <Metric label="Recovery triggered" value={recoveryTriggeredOrders.length} />
              <Metric label="Recovery target hit" value={recoveryTargetOrders.length} />
              <Metric label="Active recovery" value={hasActiveRecovery ? 'yes' : 'no'} />
              <p className="mt-4 text-xs uppercase tracking-wide text-gray-400">Recovery notes</p>
              {nearMissOrders.length > 0 ? (
                <p className="mt-1 text-sm text-gray-300">
                  Recovery plans are simulated only and can be seen on each order row.
                </p>
              ) : (
                <p className="mt-1 text-sm text-gray-500">No recovery or recovery-miss events to show.</p>
              )}
            </Panel>

            <Panel title="Open / Completed / Near-miss">
              <Metric label="Open orders" value={openOrders.length} />
              <Metric label="Completed outcomes" value={completedOrders.length} />
              <Metric label="Near-miss orders" value={nearMissOrders.length} />
              <Metric label="Signal allowed" value={run.signal_allowed ? 'true' : 'false'} />
              <Metric label="Research only" value={run.research_only ? 'true' : 'false'} />
              {nearMissOrders.length > 0 && (
                <div className="mt-4 space-y-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Near-miss rows</p>
                  {nearMissOrders.map((order) => (
                    <div key={order.order_id} className="rounded-md border border-amber-900 bg-amber-950 p-3">
                      <div className="flex flex-wrap gap-2 text-sm">
                        <span className="font-medium text-white">{order.order_id}</span>
                        <StatusTag status={order.status} />
                        <span className="text-gray-300">{order.side}</span>
                      </div>
                      <p className="mt-2 text-sm text-gray-300">
                        closest entry touch: {formatNumber(order.closest_price_to_entry)} at{' '}
                        {formatDate(order.closest_time_to_entry)}
                      </p>
                      <p className="mt-1 text-sm text-gray-300">
                        distance={formatNumber(order.near_miss_distance_points)} threshold=
                        {formatNumber(order.near_miss_threshold_points)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          <Panel title="Source quality and limitations">
            <div className="grid grid-cols-1 gap-4 text-sm md:grid-cols-2">
              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-gray-400">Missing inputs</p>
                <NotesList notes={run.missing_inputs} />
              </div>
              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-gray-400">Limitations</p>
                <NotesList notes={run.limitations} />
              </div>
              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-gray-400">No-signal reasons</p>
                <NotesList notes={run.no_signal_reasons} />
              </div>
              <div>
                <p className="mb-2 text-xs uppercase tracking-wide text-gray-400">Data provenance</p>
                <p className="text-sm text-gray-300">
                  Bars and snapshot artifacts are local file artifacts from the feature-026 run.
                </p>
              </div>
            </div>
          </Panel>

          {run.artifact_paths.length > 0 && (
            <Panel title="Artifacts">
              <ul className="grid grid-cols-1 gap-2 text-sm">
                {run.artifact_paths.map((artifactPath) => (
                  <li key={artifactPath} className="rounded-md border border-white/10 bg-white/[0.03] p-2">
                    {artifactPath}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </>
      )}
    </div>
  )
}

function RunSummary({ run }: { run: XauPlanTrackerRunResult }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
      <Metric label="Run ID" value={run.run_id} />
      <Metric label="Session Date" value={run.session_date} />
      <Metric label="Created" value={formatDate(run.created_at)} />
      <Metric label="Readiness" value={run.readiness} />
      <Metric label="Snapshots" value={run.snapshot_count} />
      <Metric label="Tracked orders" value={run.tracked_order_count} />
      <Metric label="Open orders" value={run.open_order_count} />
      <Metric label="Completed orders" value={run.completed_order_count} />
    </div>
  )
}

function PlanSnapshotCard({ snapshot }: { snapshot: XauPlanTrackerSnapshot }) {
  return (
    <Panel title={`Plan snapshot ${formatTime(snapshot.planning_time)}`}>
      <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
        <Metric label="Planning time" value={formatDate(snapshot.planning_time)} />
        <Metric label="Alignment" value={snapshot.reference_alignment} />
        <Metric label="Future reference" value={formatNumber(snapshot.future_reference_price)} />
        <Metric label="Traded reference" value={formatNumber(snapshot.traded_reference_price)} />
        <Metric label="Diff points" value={formatSignedNumber(snapshot.diff_points)} />
        <Metric label="DTE" value={formatNumber(snapshot.dte)} />
      </dl>
      <div className="mt-4 grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
        <Metric label="Native 1SD" value={formatNumber(snapshot.native_1sd)} />
        <Metric label="Native 2SD" value={formatNumber(snapshot.native_2sd)} />
        <Metric label="Native 3SD" value={formatNumber(snapshot.native_3sd)} />
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
        <PlanCard title="Long plan" plan={snapshot.long_plan} />
        <PlanCard title="Short plan" plan={snapshot.short_plan} />
      </div>
      <div className="mt-4">
        <p className="mb-2 text-xs uppercase tracking-wide text-gray-400">Snapshot notes</p>
        <NotesList notes={[...snapshot.missing_inputs, ...snapshot.limitations]} />
      </div>
    </Panel>
  )
}

function PlanCard({
  plan,
  title,
}: {
  plan: XauPlanTrackerSnapshot['long_plan'] | null
  title: string
}) {
  if (!plan) {
    return (
      <div className="rounded-md border border-dashed border-white/20 p-3">
        <p className="text-xs uppercase tracking-wide text-gray-400">{title}</p>
        <p className="mt-2 text-sm text-gray-400">Plan unavailable (missing inputs).</p>
      </div>
    )
  }

  return (
    <div className="rounded-md border border-white/10 p-3">
      <p className="mb-2 text-xs uppercase tracking-wide text-gray-400">{title}</p>
      <dl className="space-y-1 text-sm">
        <Metric label="Entry" value={formatNumber(plan.entry_level)} />
        <Metric label="Target" value={formatNumber(plan.target_level)} />
        <Metric label="Stop" value={formatNumber(plan.stop_level)} />
        {plan.recovery_entry_level !== null && (
          <Metric label="Recovery entry" value={formatNumber(plan.recovery_entry_level)} />
        )}
        {plan.recovery_target_level !== null && (
          <Metric label="Recovery target" value={formatNumber(plan.recovery_target_level)} />
        )}
      </dl>
    </div>
  )
}

function OrdersTable({ orders }: { orders: XauPlanTrackerOrder[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="text-xs uppercase text-gray-400">
          <tr>
            <th className="px-3 py-2">Order</th>
            <th className="px-3 py-2">Side</th>
            <th className="px-3 py-2">Entry</th>
            <th className="px-3 py-2">Target</th>
            <th className="px-3 py-2">Stop</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Trigger</th>
            <th className="px-3 py-2">Exit</th>
            <th className="px-3 py-2">Current</th>
            <th className="px-3 py-2">PnL</th>
            <th className="px-3 py-2">DD</th>
            <th className="px-3 py-2">Flags</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.order_id} className="border-t border-white/10 align-top">
              <td className="px-3 py-2">
                <div>
                  <p className="font-medium text-white">{order.order_id}</p>
                  <p className="text-xs text-gray-400">{formatTime(order.planning_time)}</p>
                </div>
              </td>
              <td className="px-3 py-2">
                <span className="rounded border border-white/10 px-2 py-1">{order.side}</span>
              </td>
              <td className="px-3 py-2">{formatNumber(order.entry_level)}</td>
              <td className="px-3 py-2">{formatNumber(order.target_level)}</td>
              <td className="px-3 py-2">{formatNumber(order.stop_level)}</td>
              <td className="px-3 py-2">
                <StatusTag status={order.status} />
              </td>
              <td className="px-3 py-2">{formatDate(order.trigger_time)}</td>
              <td className="px-3 py-2">{formatDate(order.exit_time)}</td>
              <td className="px-3 py-2">{formatNumber(order.current_price)}</td>
              <td className="px-3 py-2">
                <span className={order.current_pnl_points === null ? '' : pnlColor(order.current_pnl_points)}>
                  {formatSignedNumber(order.current_pnl_points)}
                </span>
              </td>
              <td className="px-3 py-2">{formatSignedNumber(order.drawdown_points)}</td>
              <td className="px-3 py-2">
                <div className="flex flex-wrap gap-2">
                  <Flag active={order.strict_triggered} label="strict" />
                  <Flag active={order.near_miss} label="near-miss" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <dl className="rounded border border-white/10 bg-black/20 p-2">
      <dt className="text-xs uppercase text-gray-400">{label}</dt>
      <dd className="mt-1 text-white">{value}</dd>
    </dl>
  )
}

function Flag({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs ${
        active
          ? 'border border-emerald-300/30 bg-emerald-400/10 text-emerald-100'
          : 'border border-zinc-700 bg-zinc-900 text-zinc-500'
      }`}
    >
      {label}
    </span>
  )
}

function NotesList({ notes }: { notes: string[] }) {
  if (notes.length === 0) {
    return <p className="text-sm text-gray-400">No entries.</p>
  }
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-gray-300">
      {notes.map((note) => (
        <li key={note}>{note}</li>
      ))}
    </ul>
  )
}

function StatusTag({ status }: { status: XauPlanTrackerOrderStatus }) {
  const classes =
    status === 'target_hit' || status === 'recovery_target_hit'
      ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-100'
      : status === 'stop_hit' || status === 'expired'
        ? 'border-red-400/40 bg-red-500/10 text-red-200'
        : status === 'open' || status === 'recovery_triggered'
          ? 'border-sky-400/40 bg-sky-400/10 text-sky-100'
          : 'border-amber-400/40 bg-amber-400/10 text-amber-100'

  return <span className={`rounded border px-2 py-1 text-xs ${classes}`}>{status}</span>
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

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md bg-gray-800 p-4">
      <h3 className="mb-4 text-base font-semibold">{title}</h3>
      {children}
    </section>
  )
}

function formatNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) return 'n/a'
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatSignedNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) return 'n/a'
  return value.toLocaleString(undefined, { maximumFractionDigits: 2, signDisplay: 'always' })
}

function formatDate(value: string | null): string {
  if (!value) return 'n/a'
  const date = new Date(value)
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
}

function formatTime(value: string): string {
  const date = new Date(value)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function pnlColor(value: number): string {
  return value >= 0 ? 'text-emerald-300' : 'text-rose-300'
}

