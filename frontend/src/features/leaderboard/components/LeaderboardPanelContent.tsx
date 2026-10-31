import { useEffect, useMemo, useState } from 'react';
import { useStore } from '../../../hooks/useStore';
import { selectScores, selectHost } from '../../game/selectors';
import { selectPlayerNickname } from '../../connection/selectors';
import { selectRetroMode } from '../../ui/selectors';
import { HostIndicator } from '../../../components/ui/HostIndicator';

function Confetti(): JSX.Element {
  return (
    <div
      data-testid="confetti"
      className="pointer-events-none absolute inset-0 flex items-start justify-center animate-fade-out motion-reduce:animate-none"
    >
      <span className="text-4xl">🎉</span>
    </div>
  );
}

export default function LeaderboardPanelContent(): JSX.Element {
  const scores = useStore(selectScores);
  const myNickname = useStore(selectPlayerNickname);
  const hostNickname = useStore(selectHost);
  const retroMode = useStore(selectRetroMode);
  const sorted = useMemo(
    () => Object.entries(scores).sort((a, b) => b[1] - a[1]),
    [scores],
  );

  const [prevLeader, setPrevLeader] = useState<string | null>(null);
  const [showConfetti, setShowConfetti] = useState(false);

  useEffect(() => {
    if (sorted.length === 0) return;
    const leader = sorted[0][0];
    if (prevLeader && leader !== prevLeader) {
      setShowConfetti(true);
      const t = setTimeout(() => setShowConfetti(false), 2000);
      return () => clearTimeout(t);
    }
    setPrevLeader(leader);
  }, [sorted, prevLeader]);

  if (retroMode) {
    if (sorted.length === 0) {
      return (
        <div className="text-center py-8">
          <p className="font-display text-retro-text-muted uppercase tracking-wider">
            Awaiting passengers...
          </p>
        </div>
      );
    }

    return (
      <div className="relative">
        {showConfetti && <Confetti />}

        {/* Header row */}
        <div className="flex justify-between px-3 py-2 border-b border-retro-border bg-retro-panel-dark font-display text-xs text-retro-text-muted uppercase tracking-wider">
          <span>Passenger</span>
          <span>Score</span>
        </div>

        {/* Player rows */}
        <ul>
          {sorted.map(([nick, score], i) => (
            <li
              key={nick}
              className={`flex justify-between items-center px-3 py-2 border-b border-retro-border last:border-none ${
                nick === myNickname ? 'bg-retro-panel' : ''
              }`}
            >
              <span className="flex items-center gap-3">
                <span className="font-splitflap text-retro-led w-6">{i + 1}</span>
                <span className="font-display text-retro-text">{nick}</span>
                <HostIndicator isHost={nick === hostNickname} variant="inline" />
              </span>
              <span className="font-splitflap text-retro-led-bright text-lg">{score}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (sorted.length === 0) {
    return <p>No players yet…</p>;
  }

  return (
    <div className="relative">
      {showConfetti && <Confetti />}
      <ul>
        {sorted.map(([nick, score]) => (
          <li
            key={nick}
            className={`flex justify-between border-b border-gray-700 py-2 last:border-none ${
              nick === myNickname ? 'font-bold' : ''
            }`}
          >
            <span className="flex items-center gap-2">
              <span>{nick}</span>
              <HostIndicator isHost={nick === hostNickname} variant="inline" />
            </span>
            <span>{score}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
