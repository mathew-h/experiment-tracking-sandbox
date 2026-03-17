import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Primary brand — deep navy
        navy: {
          950: '#020c18',
          900: '#05172B',
          800: '#0a2440',
          700: '#0e3158',
          600: '#133e70',
          500: '#184b88',
        },
        // Accent — warm red
        red: {
          600: '#d93020',
          500: '#FD4437',
          400: '#ff6b5e',
          300: '#ff9289',
        },
        // Surface hierarchy (navy-based)
        surface: {
          base:    '#05172B',
          raised:  '#0a2440',
          overlay: '#0e3158',
          border:  '#1a3a5c',
          muted:   '#133355',
        },
        // Text hierarchy
        ink: {
          primary:   '#F0F4F8',
          secondary: '#8BACC8',
          muted:     '#4d6e8a',
          accent:    '#FD4437',
        },
        // Status colors
        status: {
          success: '#22c55e',
          warning: '#f59e0b',
          error:   '#FD4437',
          info:    '#38bdf8',
          ongoing: '#22c55e',
          completed: '#38bdf8',
          cancelled: '#6b7280',
        },
      },
      fontFamily: {
        sans:  ['Inter', 'system-ui', 'sans-serif'],
        mono:  ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        display: ['Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
      },
      spacing: {
        '18': '4.5rem',
        '72': '18rem',
        '80': '20rem',
      },
      borderRadius: {
        sm: '2px',
        DEFAULT: '4px',
        md: '6px',
        lg: '8px',
        xl: '12px',
      },
      boxShadow: {
        'glow-red':   '0 0 12px rgba(253, 68, 55, 0.35)',
        'glow-blue':  '0 0 12px rgba(56, 189, 248, 0.25)',
        'panel':      '0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.6)',
        'panel-lg':   '0 4px 16px rgba(0,0,0,0.5)',
        'inset-top':  'inset 0 1px 0 rgba(255,255,255,0.06)',
      },
      backgroundImage: {
        'grid-navy': `linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)`,
        'gradient-navy': 'linear-gradient(180deg, #0a2440 0%, #05172B 100%)',
      },
      backgroundSize: {
        'grid': '24px 24px',
      },
      animation: {
        'fade-in':    'fadeIn 0.2s ease-out',
        'slide-in':   'slideIn 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-up':   'slideUp 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow':  'spin 2s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideIn: {
          '0%':   { transform: 'translateX(-8px)', opacity: '0' },
          '100%': { transform: 'translateX(0)',    opacity: '1' },
        },
        slideUp: {
          '0%':   { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',   opacity: '1' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
