import type { Metadata } from 'next'
import './globals.css'
import Header from '@/components/ui/Header'

export const metadata: Metadata = {
  title: 'Elpis OI Regime Lab',
  description: 'Research dashboard for crypto market regime classification',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-950 text-zinc-50 antialiased">
        <Header />
        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </body>
    </html>
  )
}
