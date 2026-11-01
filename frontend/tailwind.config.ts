import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  // Belt-and-suspenders: even if the content scanner misses dynamic class
  // strings in lib/tools.ts, these stay in the build.
  safelist: [
    'text-yellow-400', 'border-yellow-400/30', 'bg-yellow-400/10',
    'text-emerald-400', 'border-emerald-400/30', 'bg-emerald-400/10',
    'text-violet-400', 'border-violet-400/30', 'bg-violet-400/10',
  ],
  theme: {
    extend: {
      colors: {
        // ORNL-inspired accent: electric blue on dark grey
        herald: {
          bg:       '#0f1117',
          surface:  '#1a1d27',
          border:   '#2a2d3a',
          accent:   '#4f8ef7',
          'accent-hover': '#3a7ae8',
          muted:    '#6b7280',
          text:     '#e2e8f0',
          'text-dim': '#94a3b8',
        },
        tool: {
          sql:      '#f59e0b',
          rag:      '#10b981',
          jobpred:  '#8b5cf6',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}

export default config
