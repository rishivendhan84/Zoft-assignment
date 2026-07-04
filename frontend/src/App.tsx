import { useEffect } from 'react';
import { useStore } from './store/useStore';
import { Sidebar } from './components/Sidebar';
import { ChatPanel } from './components/ChatPanel';
import { WorkflowPanel } from './components/WorkflowPanel';
import { Toasts } from './components/Toasts';

export default function App() {
  const init = useStore((s) => s.init);

  useEffect(() => {
    init();
  }, [init]);

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col border-x border-zinc-200 dark:border-zinc-800">
        <ChatPanel />
      </main>
      <WorkflowPanel />
      <Toasts />
    </div>
  );
}
