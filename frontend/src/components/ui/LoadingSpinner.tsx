'use client'

export default function LoadingSpinner() {
  return (
    <div className="flex min-h-80 items-center justify-center p-8">
      <div className="flex flex-col items-center gap-4 rounded-md border border-white/10 bg-white/[0.04] px-8 py-7 shadow-2xl shadow-black/20">
        <div className="h-12 w-12 animate-spin rounded-full border-2 border-zinc-700 border-t-sky-300" />
        <div className="text-center">
          <p className="text-sm font-medium text-zinc-100">Loading research workspace</p>
          <p className="mt-1 text-xs text-zinc-400">Checking local market data and feature state.</p>
        </div>
      </div>
    </div>
  )
}
