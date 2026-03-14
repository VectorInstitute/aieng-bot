import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'vector-magenta':   '#EB088A',
        'vector-violet':    '#8A25C9',
        'vector-cobalt':    '#313CFF',
        'vector-turquoise': '#48C0D9',
        'vector-black':     '#000000',
        'vector-grey':      '#E9E8E8',
      },
      animation: {
        'fade-in':  'fadeIn 0.3s ease-in',
        'slide-up': 'slideUp 0.4s ease-out',
        'pulse-dot': 'pulseDot 1.2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn:   { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideUp:  { '0%': { transform: 'translateY(12px)', opacity: '0' }, '100%': { transform: 'translateY(0)', opacity: '1' } },
        pulseDot: { '0%, 100%': { opacity: '0.3' }, '50%': { opacity: '1' } },
      },
      backgroundImage: {
        'vector-gradient': 'linear-gradient(135deg, #EB088A 0%, #8A25C9 50%, #313CFF 100%)',
      },
      typography: {
        DEFAULT: {
          css: {
            color: '#cbd5e1',
            a: { color: '#8A25C9' },
            strong: { color: '#f1f5f9' },
            code: { color: '#e2e8f0', backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: '4px', padding: '2px 4px' },
            'code::before': { content: '""' },
            'code::after':  { content: '""' },
            pre: { backgroundColor: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' },
            blockquote: { color: '#94a3b8', borderLeftColor: '#8A25C9' },
            h1: { color: '#f1f5f9' },
            h2: { color: '#f1f5f9' },
            h3: { color: '#f1f5f9' },
          },
        },
      },
    },
  },
  plugins: [],
}

export default config
