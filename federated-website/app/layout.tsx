import React from "react"
import type { Metadata } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import './globals.css'
import { Navbar } from '@/components/navbar'
import { Footer } from '@/components/footer'

const _inter = Inter({ subsets: ["latin"] });
const _jetbrainsMono = JetBrains_Mono({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: 'FedWind - Privacy-Preserving Wind Forecasting',
  description: 'Federated Learning and LLM-based Wind Speed and Wind Power Forecasting System. A university research project for privacy-preserving collaborative wind forecasting.',
  keywords: ['Federated Learning', 'Wind Forecasting', 'LLM', 'Machine Learning', 'Privacy', 'Renewable Energy'],
  icons: {
    icon: [
      // {
      //   url: '/.png',
      //   media: '(prefers-color-scheme: light)',
      // },
      // {
      //   url: '/.png',
      //   media: '(prefers-color-scheme: dark)',
      // },
      // {
      //   url: '/icon.svg',
      //   type: 'image/svg+xml',
      // },
    ],
    // apple: '/.png',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`font-sans antialiased min-h-screen flex flex-col`}>
        <Navbar />
        <main className="flex-1">
          {children}
        </main>
        <Footer />
      </body>
    </html>
  )
}
