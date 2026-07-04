import { useStore } from '../store/useStore';

export function HealthDot() {
  const backendUp = useStore((s) => s.backendUp);
  const color =
    backendUp === null ? 'bg-zinc-400' : backendUp ? 'bg-emerald-500' : 'bg-red-500';
  const label =
    backendUp === null ? 'Checking backend…' : backendUp ? 'Backend online' : 'Backend unreachable';
  return (
    <span className="relative flex h-2 w-2" title={label} aria-label={label}>
      {backendUp && (
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
      )}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
    </span>
  );
}
