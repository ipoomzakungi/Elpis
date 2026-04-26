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
      <body className="bg-gray-950 text-white min-h-screen">
        <Header />
        <main className="container mx-auto p-4">
          {children}
        </main>
      </body>
    </html>
  )
}
