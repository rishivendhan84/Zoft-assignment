import { useStore } from '../store/useStore';
import { MoonIcon, SunIcon } from './icons';

export function ThemeToggle() {
  const theme = useStore((s) => s.theme);
  const toggleTheme = useStore((s) => s.toggleTheme);
  return (
    <button
      onClick={toggleTheme}
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      className="rounded-md p-1 text-zinc-400 transition-colors hover:bg-zinc-200/60 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
    >
      {theme === 'dark' ? <SunIcon size={14} /> : <MoonIcon size={14} />}
    </button>
  );
}
