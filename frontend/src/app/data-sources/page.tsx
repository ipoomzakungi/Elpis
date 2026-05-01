export default function DataSourcesPage() {
  return (
    <main className="min-h-screen bg-gray-50 text-gray-950">
      <section className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-gray-500">
            Research Data Onboarding
          </p>
          <h2 className="mt-2 text-2xl font-semibold">Data Sources</h2>
        </div>

        <div className="rounded border border-gray-200 bg-white p-4">
          <h3 className="text-base font-semibold">Foundation placeholder</h3>
          <p className="mt-2 text-sm leading-6 text-gray-700">
            This page is reserved for the feature 008 data-source readiness workflow. It
            will show public source availability, optional research provider key status,
            local-file requirements, missing-data actions, and first evidence run links in
            later slices.
          </p>
        </div>

        <p className="text-sm text-gray-600">
          Research-only. This page does not enable live trading, paper trading, shadow
          trading, broker integration, private trading keys, wallet handling, or order
          execution.
        </p>
      </section>
    </main>
  );
}
