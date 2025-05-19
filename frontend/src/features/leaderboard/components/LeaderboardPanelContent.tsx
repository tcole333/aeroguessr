import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../../../hooks/useStore';
import { selectScores } from '../../game/selectors';

function Confetti(): JSX.Element {
  return (
    <motion.div
      data-testid="confetti"
      className="pointer-events-none absolute inset-0 flex items-start justify-center"
      initial={{ opacity: 1 }}
      animate={{ opacity: 0 }}
      transition={{ duration: 2 }}
    >
      <span className="text-4xl">🎉</span>
    </motion.div>
  );
}

export default function LeaderboardPanelContent(): JSX.Element {
  const scores = useStore(selectScores);
  const myNickname = useStore(
    (s) => (s.connection as unknown as { nickname?: string }).nickname,
  );
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
            <span>{nick}</span>
            <span>{score}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
