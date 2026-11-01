import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'HERALD — HPC Operations Assistant',
  description: 'AI assistant for HPC operational data analytics',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">{children}</body>
    </html>
  )
}
