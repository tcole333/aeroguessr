import React from 'react';

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
  if (!isHost) return null;

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
