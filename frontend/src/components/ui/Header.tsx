'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/', label: 'Dashboard' },
  { href: '/backtests', label: 'Backtests' },
  { href: '/research', label: 'Research' },
  { href: '/evidence', label: 'Evidence' },
  { href: '/xau-plan-tracker', label: 'XAU Plan Tracker' },
  { href: '/data-sources', label: 'Data Sources' },
]

export default function Header() {
  const pathname = usePathname()

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-zinc-950/80 text-white backdrop-blur">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
        <Link href="/" className="group flex min-w-0 items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-sky-400/30 bg-sky-400/10 text-sm font-bold text-sky-200 transition group-hover:border-sky-300">
            EL
          </span>
          <span className="min-w-0">
            <span className="block truncate text-base font-semibold tracking-normal">Elpis OI Regime Lab</span>
            <span className="block text-xs text-zinc-400">Research dashboard</span>
          </span>
        </Link>
        <nav className="flex flex-wrap items-center gap-2 text-sm">
          {navItems.map((item) => {
            const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-2 transition ${
                  active
                    ? 'bg-white text-zinc-950 shadow-sm'
                    : 'text-zinc-300 hover:bg-white/10 hover:text-white'
                }`}
              >
                {item.label}
              </Link>
            )
          })}
          <span className="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-medium text-emerald-200">
            v0 research only
          </span>
        </nav>
      </div>
    </header>
  )
}
