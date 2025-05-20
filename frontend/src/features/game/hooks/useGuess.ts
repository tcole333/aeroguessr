import { useState, useEffect, useCallback } from 'react';
import { useStore } from '../../../hooks/useStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';
import { selectRound, selectRoundTimeout } from '../selectors';
import { selectConnectionStatus } from '../../connection/selectors';

export interface UseGuessResult {
  code: string;
  disabled: boolean;
  error: string | null;
  remaining: number | null;
  visible: boolean;
  setCode: (val: string) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  dismiss: () => void;
}

export function useGuess(): UseGuessResult {
  const round = useStore(selectRound);
  const timeout = useStore(selectRoundTimeout);
  const status = useStore(selectConnectionStatus);

  const [code, setCode] = useState('');
  const [hasGuessed, setHasGuessed] = useState(false);
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    if (round && round.state === 'guessing') {
      setVisible(true);
      setCode('');
      setHasGuessed(false);
      setError(null);
      if (timeout != null) {
        const end = Date.now() + timeout * 1000;
        setRemaining(timeout);
        const t = setInterval(() => {
          const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
          setRemaining(left);
        }, 1000);
        return () => clearInterval(t);
      }
    } else {
      setVisible(false);
      setHasGuessed(false);
      setRemaining(null);
    }
    return undefined;
  }, [round, timeout]);

  const disabled = hasGuessed || status !== 'connected';

  const submit = useCallback(() => {
    const trimmed = code.trim().toUpperCase();
    if (!trimmed) {
      setError('Airport code required');
      return;
    }
    try {
      webSocketClient.send({ type: 'guess', payload: { airport_code: trimmed } });
      setHasGuessed(true);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [code]);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (disabled) return;
    submit();
  };

  const dismiss = () => {
    if (!hasGuessed) setVisible(false);
  };

  return {
    code,
    disabled,
    error,
    remaining,
    visible,
    setCode: (v: string) => setCode(v.toUpperCase()),
    handleSubmit,
    dismiss,
  };
}
