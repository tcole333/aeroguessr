import React from 'react';
import { useStore } from '../../hooks/useStore';
import { selectRetroMode } from '../../features/ui/selectors';

interface HostIndicatorProps {
  isHost: boolean;
  variant?: 'badge' | 'inline';
  className?: string;
}

export const HostIndicator: React.FC<HostIndicatorProps> = ({
  isHost,
  variant = 'badge',
  className = ''
}) => {
  const retroMode = useStore(selectRetroMode);

  if (!isHost) return null;

  // Retro theme styling
  if (retroMode) {
    const baseClasses = variant === 'badge'
      ? 'px-2 py-1 text-xs font-display uppercase tracking-wider border border-retro-primary text-retro-primary-dark bg-retro-panel-dark'
      : 'px-1.5 py-0.5 text-xs font-display uppercase tracking-wider border border-retro-primary text-retro-primary-dark bg-retro-panel-dark';

    return (
      <span
        className={`${baseClasses} ${className}`}
        role="status"
        aria-label="Host player"
        title={variant === 'inline' ? 'Host' : undefined}
      >
        Host
      </span>
    );
  }

  if (variant === 'badge') {
    return (
      <span
        className={`px-2 py-1 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 ${className}`}
        role="status"
        aria-label="Host player"
      >
        Host
      </span>
    );
  }

  // Inline variant - smaller version
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 ${className}`}
      role="status"
      aria-label="Host player"
      title="Host"
    >
      Host
    </span>
  );
};
