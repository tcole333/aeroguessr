import React, { useState } from 'react';
import { selectRoomCode } from '../../features/connection/connectionSlice';
import { useStore } from '../../hooks/useStore';
import { selectRetroMode } from '../../features/ui/selectors';

interface RoomCodeDisplayProps {
  className?: string;
}

export const RoomCodeDisplay: React.FC<RoomCodeDisplayProps> = ({ className = '' }) => {
  const roomCode = useStore(selectRoomCode);
  const retroMode = useStore(selectRetroMode);
  const [copied, setCopied] = useState(false);

  if (!roomCode || roomCode === 'solo') {
    return null; // Don't show for solo mode or when no room code
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(roomCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy room code:', err);
    }
  };

  if (retroMode) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <span className="text-sm font-display uppercase tracking-wider text-retro-text-muted">Room:</span>
        <button
          onClick={handleCopy}
          className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-retro-forest bg-retro-panel-dark px-2 py-1 border border-retro-border hover:border-retro-primary transition-colors"
          aria-label={`Room code ${roomCode}. Click to copy`}
          title="Click to copy room code"
        >
          {roomCode}
        </button>
        {copied && (
          <span className="text-xs text-retro-success animate-fade-in">
            Copied!
          </span>
        )}
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="text-sm text-gray-600 dark:text-gray-400">Room:</span>
      <button
        onClick={handleCopy}
        className="font-mono text-sm font-semibold text-gray-800 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        aria-label={`Room code ${roomCode}. Click to copy`}
        title="Click to copy room code"
      >
        {roomCode}
      </button>
      {copied && (
        <span className="text-xs text-green-600 dark:text-green-400 animate-fade-in">
          Copied!
        </span>
      )}
    </div>
  );
};
