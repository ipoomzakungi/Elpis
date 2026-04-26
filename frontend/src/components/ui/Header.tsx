'use client'

import { useState } from 'react'

export default function Header() {
  return (
    <header className="bg-gray-900 text-white p-4">
      <div className="container mx-auto flex justify-between items-center">
        <h1 className="text-2xl font-bold">Elpis OI Regime Lab</h1>
        <nav className="flex gap-4">
          <span className="text-sm text-gray-400">v0 Research Dashboard</span>
        </nav>
      </div>
    </header>
  )
}
