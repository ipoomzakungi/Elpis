import BacktestSummaryCards from '@/components/panels/BacktestSummaryCards'

export default function BacktestsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">Backtest Reports</h2>
        <p className="mt-2 text-sm text-gray-400">
          Historical simulation reports will appear here after the backtest API is implemented.
        </p>
      </div>
      <BacktestSummaryCards />
      <div className="bg-gray-800 rounded-lg p-4 text-sm text-gray-400">
        No completed backtest runs are loaded yet.
      </div>
    </div>
  )
}