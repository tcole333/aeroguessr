import { useState } from 'react';
import { useStore } from '../../../hooks/useStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';
import {
  selectHost,
  selectIsSolo,
  selectSelectedPlane,
} from '../../game/selectors';
import {
  selectNickname,
  selectConnectionStatus,
} from '../../connection/selectors';

export default function HostControls(): JSX.Element | null {
  const host = useStore(selectHost);
  const isSolo = useStore(selectIsSolo);
  const myNick = useStore(selectNickname);
  const status = useStore(selectConnectionStatus);
  const selected = useStore(selectSelectedPlane);

  const isHost = !isSolo && host && myNick === host;
  const disabled = status !== 'connected' || !isHost;

  const [transferNick, setTransferNick] = useState('');

  const handleStart = () => {
    if (disabled || !selected) return;
    webSocketClient.send({ type: 'startRound', payload: {} });
  };

  const handleSkip = () => {
    if (disabled) return;
    webSocketClient.send({ type: 'skipRound', payload: {} });
  };

  const handleTransfer = () => {
    const nick = transferNick.trim();
    if (disabled || !nick) return;
    webSocketClient.send({ type: 'transferHost', payload: { to_nickname: nick } });
    setTransferNick('');
  };

  if (!isHost) return null;

  return (
    <div className="space-y-2" data-testid="host-controls">
      <p className="text-sm text-gray-700 dark:text-gray-300">Selected: {selected ?? 'None'}</p>
      <button
        type="button"
        className="w-full rounded bg-blue-500 py-1 text-white disabled:bg-gray-400"
        disabled={disabled || !selected}
        onClick={handleStart}
      >
        Start Round
      </button>
      <button
        type="button"
        className="w-full rounded bg-yellow-500 py-1 text-white disabled:bg-gray-400"
        disabled={disabled}
        onClick={handleSkip}
      >
        Skip Round
      </button>
      <div className="flex space-x-2">
        <input
          type="text"
          value={transferNick}
          onChange={(e) => setTransferNick(e.target.value)}
          className="flex-1 border p-1 text-black"
          placeholder="Nickname"
        />
        <button
          type="button"
          className="rounded bg-purple-500 px-2 py-1 text-white disabled:bg-gray-400"
          disabled={disabled || transferNick.trim() === ''}
          onClick={handleTransfer}
        >
          Transfer
        </button>
      </div>
    </div>
  );
}
