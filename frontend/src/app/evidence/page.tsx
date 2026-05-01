'use client';

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { api } from '@/services/api';
import {
  ResearchExecutionDashboardData,
  ResearchExecutionRunSummary,
  ResearchExecutionWorkflowResult,
} from '@/types';

const STATUS_LABELS = ['completed', 'partial', 'blocked', 'skipped', 'failed'] as const;

export default function EvidencePage() {
  const [runs, setRuns] = useState<ResearchExecutionRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [data, setData] = useState<ResearchExecutionDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadRuns() {
      setIsLoading(true);
      setError(null);
      try {
        const response = await api.getResearchExecutionRuns();
        if (cancelled) return;
        setRuns(response.runs);
        if (response.runs.length > 0) {
          setSelectedRunId((current) => current || response.runs[0].execution_run_id);
        } else {
          setData(null);
          setIsLoading(false);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Unable to load evidence reports');
        setIsLoading(false);
      }
    }
    loadRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    let cancelled = false;
    async function loadSelectedRun() {
      setIsLoading(true);
      setError(null);
      try {
        const response = await api.getResearchExecutionDashboardData(selectedRunId);
        if (cancelled) return;
        setData(response);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Unable to load selected evidence report');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    loadSelectedRun();
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  const workflowResults = data?.evidence.workflow_results ?? [];
  const reportReferences = useMemo(() => collectReportReferences(workflowResults), [workflowResults]);
  const missingData = data?.missingData.missing_data_checklist ?? [];
  const limitations = data?.evidence.limitations ?? [];
  const warnings = data?.evidence.research_only_warnings ?? [];

  return (
    <main className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100 sm:px-6">
      <div className="mx-auto flex max-w-7xl flex-col gap-5">
        <header className="flex flex-col gap-4 border-b border-slate-800 pb-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-sm font-medium uppercase text-sky-300">Research execution</p>
            <h1 className="mt-2 text-2xl font-semibold sm:text-3xl">Evidence reports</h1>
          </div>
          <label className="flex flex-col gap-2 text-sm text-slate-300">
            <span>Execution run</span>
            <select
              value={selectedRunId}
              onChange={(event) => setSelectedRunId(event.target.value)}
              className="min-w-80 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-sky-400"
            >
              {runs.length === 0 ? (
                <option value="">No saved runs</option>
              ) : (
                runs.map((run) => (
                  <option key={run.execution_run_id} value={run.execution_run_id}>
                    {run.name || run.execution_run_id}
                  </option>
                ))
              )}
            </select>
          </label>
        </header>

        {error ? (
          <section className="rounded-md border border-red-400/40 bg-red-950/30 p-4 text-sm text-red-100">
            {error}
          </section>
        ) : null}

        {isLoading ? (
          <section className="rounded-md border border-slate-800 bg-slate-900/70 p-5 text-sm text-slate-300">
            Loading evidence report...
          </section>
        ) : null}

        {!isLoading && !data ? (
          <section className="rounded-md border border-slate-800 bg-slate-900/70 p-5 text-sm text-slate-300">
            No research execution reports found.
          </section>
        ) : null}

        {data ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <StatusCard label="Decision" value={formatValue(data.evidence.decision)} />
              {STATUS_LABELS.map((status) => (
                <StatusCard
                  key={status}
                  label={formatValue(status)}
                  value={String(data.statusCounts[status])}
                />
              ))}
            </section>

            <section className="rounded-md border border-slate-800 bg-slate-900/70 p-4">
              <h2 className="text-lg font-semibold">Workflow decisions</h2>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-slate-800 text-xs uppercase text-slate-400">
                    <tr>
                      <th className="px-3 py-2">Workflow</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Decision</th>
                      <th className="px-3 py-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {workflowResults.map((workflow) => (
                      <tr key={workflow.workflow_type}>
                        <td className="px-3 py-2 font-medium">{formatValue(workflow.workflow_type)}</td>
                        <td className="px-3 py-2">{formatValue(workflow.status)}</td>
                        <td className="px-3 py-2">{formatValue(workflow.decision)}</td>
                        <td className="px-3 py-2 text-slate-300">{workflow.decision_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <Panel title="Report references">
                {reportReferences.length === 0 ? (
                  <p className="text-sm text-slate-400">No linked report IDs.</p>
                ) : (
                  <ul className="space-y-2 text-sm text-slate-300">
                    {reportReferences.map((reference) => (
                      <li key={reference} className="rounded border border-slate-800 px-3 py-2">
                        {reference}
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel title="Missing data checklist">
                {missingData.length === 0 ? (
                  <p className="text-sm text-slate-400">None</p>
                ) : (
                  <ul className="space-y-2 text-sm text-amber-100">
                    {missingData.map((item) => (
                      <li key={item} className="rounded border border-amber-400/30 bg-amber-950/30 px-3 py-2">
                        {item}
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </section>

            <section className="rounded-md border border-slate-800 bg-slate-900/70 p-4">
              <h2 className="text-lg font-semibold">Workflow assets</h2>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-slate-800 text-xs uppercase text-slate-400">
                    <tr>
                      <th className="px-3 py-2">Workflow</th>
                      <th className="px-3 py-2">Asset</th>
                      <th className="px-3 py-2">Source</th>
                      <th className="px-3 py-2">Rows</th>
                      <th className="px-3 py-2">Unsupported</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {workflowResults.flatMap((workflow) =>
                      workflow.asset_results.map((asset) => (
                        <tr key={`${workflow.workflow_type}-${asset.asset}-${asset.source_identity}`}>
                          <td className="px-3 py-2">{formatValue(workflow.workflow_type)}</td>
                          <td className="px-3 py-2 font-medium">{asset.asset || 'n/a'}</td>
                          <td className="px-3 py-2">{asset.source_identity || 'n/a'}</td>
                          <td className="px-3 py-2">{asset.row_count ?? 'n/a'}</td>
                          <td className="px-3 py-2 text-slate-300">
                            {asset.unsupported_capabilities.length > 0
                              ? asset.unsupported_capabilities.join(', ')
                              : 'None'}
                          </td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <Panel title="Limitations">
                <TextList items={limitations} empty="None" />
              </Panel>
              <Panel title="Research-only warnings">
                <TextList items={warnings} empty="None" />
              </Panel>
            </section>

            <section className="rounded-md border border-amber-400/40 bg-amber-950/30 p-4 text-sm leading-6 text-amber-100">
              Evidence labels are research decisions only. They are not trading approvals
              and do not imply profitability, predictive power, safety, or live readiness.
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}

function StatusCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/70 p-4">
      <p className="text-xs uppercase text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-slate-800 bg-slate-900/70 p-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function TextList({ items, empty }: { items: string[]; empty: string }) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">{empty}</p>;
  }
  return (
    <ul className="space-y-2 text-sm text-slate-300">
      {items.map((item) => (
        <li key={item} className="rounded border border-slate-800 px-3 py-2">
          {item}
        </li>
      ))}
    </ul>
  );
}

function collectReportReferences(workflows: ResearchExecutionWorkflowResult[]): string[] {
  const references: string[] = [];
  for (const workflow of workflows) {
    for (const reportId of workflow.report_ids) {
      const label = `${formatValue(workflow.workflow_type)}: ${reportId}`;
      if (!references.includes(label)) {
        references.push(label);
      }
    }
  }
  return references;
}

function formatValue(value: string) {
  return value.replaceAll('_', ' ');
}
