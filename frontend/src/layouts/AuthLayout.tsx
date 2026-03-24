import { Outlet } from 'react-router-dom'

/** Centered card layout used for login and other unauthenticated pages. */
export function AuthLayout() {
  return (
    <div className="min-h-screen bg-surface-base flex items-center justify-center p-4 relative overflow-hidden">
      {/* Decorative grid background */}
      <div
        className="absolute inset-0 opacity-50"
        style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
                            linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)`,
          backgroundSize: '32px 32px',
        }}
      />
      {/* Radial glow behind card */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-[600px] h-[400px] bg-red-500/5 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-sm">
        {/* Logo header */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-14 h-14 rounded-xl bg-surface-overlay border border-surface-border flex items-center justify-center mb-4 shadow-panel-lg">
            <img src="/logo.png" alt="Addis Energy" className="w-9 h-9 object-contain rounded" />
          </div>
          <h1 className="text-lg font-semibold text-ink-primary">Addis Energy</h1>
          <p className="text-xs text-ink-muted mt-0.5 tracking-wider uppercase">Lab Experiment Tracker</p>
        </div>

        <Outlet />
      </div>
    </div>
  )
}
