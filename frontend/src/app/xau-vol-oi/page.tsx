export default function XauVolOiPage() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-8">
        <div>
          <p className="text-sm font-medium uppercase text-amber-300">
            Research report
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-white">XAU Vol-OI Walls</h1>
        </div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-300">
          XAU Vol-OI report inspection is being added in phases. This page is a placeholder for
          local gold options OI source validation, basis-adjusted wall levels, expected ranges, and
          research-only zone notes.
        </div>
        <div className="rounded border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-100">
          Research-only: this workflow does not provide buy/sell signals, profitability claims, or
          live-readiness guidance.
        </div>
      </section>
    </main>
  );
}
