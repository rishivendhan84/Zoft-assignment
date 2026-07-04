import type { SVGProps } from 'react';
import type { NodeCategory, Phase } from '../types';

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 16, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    ...props,
  };
}

export const BoltIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M13 2 3 14h8l-1 8 10-12h-8l1-8z" />
  </svg>
);

export const PaperPlaneIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M22 2 11 13" />
    <path d="M22 2 15 22l-4-9-9-4 20-7z" />
  </svg>
);

export const FunnelIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M22 3H2l8 9.5V19l4 2v-8.5L22 3z" />
  </svg>
);

export const SparklesIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
  </svg>
);

export const SearchIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);

export const PencilIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
  </svg>
);

export const ShieldIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

export const WrenchIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M14.7 6.3a4.5 4.5 0 0 0 6 6l-3.2 3.2a2 2 0 0 1-2.8 0l-9-9a2 2 0 0 1 0-2.8L8.9.5a4.5 4.5 0 0 0 5.8 5.8z" transform="rotate(90 12 12)" />
    <path d="m3 21 6-6" />
  </svg>
);

export const CommitIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="3.5" />
    <path d="M2 12h6.5M15.5 12H22" />
  </svg>
);

export const ChatIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z" />
  </svg>
);

export const CheckIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

export const XIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);

export const StopIcon = (p: IconProps) => (
  <svg {...base(p)} fill="currentColor" stroke="none">
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </svg>
);

export const SendIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </svg>
);

export const PlusIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const ChevronIcon = ({ open, ...p }: IconProps & { open?: boolean }) => (
  <svg {...base(p)} className={`${p.className ?? ''} transition-transform ${open ? 'rotate-90' : ''}`}>
    <path d="m9 6 6 6-6 6" />
  </svg>
);

export const AlertIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3 1.5 21h21L12 3z" />
    <path d="M12 10v4M12 18h.01" />
  </svg>
);

export const SunIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
);

export const MoonIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z" />
  </svg>
);

export const Spinner = ({ size = 16, className = '' }: { size?: number; className?: string }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    className={`animate-spin ${className}`}
  >
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.25" />
    <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

export function CategoryIcon({ category, size = 14 }: { category: NodeCategory; size?: number }) {
  if (category === 'trigger') return <BoltIcon size={size} />;
  if (category === 'logic') return <FunnelIcon size={size} />;
  return <PaperPlaneIcon size={size} />;
}

export function PhaseIcon({ phase, size = 14 }: { phase: Phase; size?: number }) {
  switch (phase) {
    case 'planning':
      return <SparklesIcon size={size} />;
    case 'retrieving':
      return <SearchIcon size={size} />;
    case 'proposing':
      return <PencilIcon size={size} />;
    case 'validating':
      return <ShieldIcon size={size} />;
    case 'repairing':
      return <WrenchIcon size={size} />;
    case 'committing':
      return <CommitIcon size={size} />;
    case 'explaining':
      return <ChatIcon size={size} />;
  }
}
