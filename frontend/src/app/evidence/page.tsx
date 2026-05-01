export default function EvidencePage() {
  return (
    <main className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <header className="border-b border-slate-800 pb-4">
          <p className="text-sm font-medium uppercase tracking-wide text-sky-300">
            Research execution
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Evidence reports</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
            This page will summarize completed, partial, blocked, skipped, and failed
            research workflows from the existing multi-asset and XAU report systems.
          </p>
        </header>

        <section className="rounded-md border border-slate-800 bg-slate-900/70 p-5">
          <h2 className="text-lg font-semibold">Foundation placeholder</h2>
          <p className="mt-2 text-sm leading-6 text-slate-300">
            Execution run selection, workflow status cards, report references, evidence
            decisions, and missing-data checklists will be wired in later 007 story slices.
          </p>
        </section>

        <section className="rounded-md border border-amber-400/40 bg-amber-950/30 p-5">
          <h2 className="text-lg font-semibold text-amber-200">Research-only</h2>
          <p className="mt-2 text-sm leading-6 text-amber-100">
            Evidence labels are research decisions only. They are not trading approvals
            and do not imply profitability, predictive power, safety, or live readiness.
          </p>
        </section>
      </div>
    </main>
  );
}
