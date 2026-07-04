import { useStore } from '../store/useStore';
import { AlertIcon, CheckIcon, XIcon } from './icons';

const tone = {
  error: 'border-red-300 bg-red-50 text-red-700 dark:border-red-500/40 dark:bg-red-950/80 dark:text-red-300',
  success:
    'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-950/80 dark:text-emerald-300',
  info: 'border-zinc-300 bg-white text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300',
};

export function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismissToast = useStore((s) => s.dismissToast);
  if (toasts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-lg animate-fade-in ${tone[t.kind]}`}
        >
          {t.kind === 'error' ? (
            <AlertIcon size={14} className="mt-0.5 shrink-0" />
          ) : (
            <CheckIcon size={14} className="mt-0.5 shrink-0" />
          )}
          <span className="min-w-0 flex-1 break-words">{t.text}</span>
          <button
            onClick={() => dismissToast(t.id)}
            className="shrink-0 opacity-50 transition-opacity hover:opacity-100"
            aria-label="Dismiss"
          >
            <XIcon size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
