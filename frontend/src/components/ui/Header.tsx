'use client'

import Link from 'next/link'

export default function Header() {
  return (
    <header className="bg-gray-900 text-white p-4">
      <div className="container mx-auto flex justify-between items-center">
        <h1 className="text-2xl font-bold">Elpis OI Regime Lab</h1>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/" className="text-gray-200 hover:text-white">
            Dashboard
          </Link>
          <Link href="/backtests" className="text-gray-200 hover:text-white">
            Backtests
          </Link>
          <span className="text-sm text-gray-400">v0 Research Dashboard</span>
        </nav>
      </div>
    </header>
  )
}
