import { useState, useEffect, useCallback } from 'react';
import { useStore } from '../../../hooks/useStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';
import { selectGuessRejection, selectRound, selectRoundTimeout } from '../selectors';
import { selectConnectionStatus } from '../../connection/selectors';
import type { Airport } from '../../../components/AirportAutocomplete';
import { guessCodeError } from '../../../lib/airportLookup';

export interface UseGuessResult {
  inputValue: string;
  selectedAirport: Airport | null;
  disabled: boolean;
  error: string | null;
  remaining: number | null;
  visible: boolean;
  setInputValue: (val: string) => void;
  setSelectedAirport: (airport: Airport | null) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  dismiss: () => void;
}

export function useGuess(): UseGuessResult {
  const round = useStore(selectRound);
  const timeout = useStore(selectRoundTimeout);
  const status = useStore(selectConnectionStatus);
  const guessRejection = useStore(selectGuessRejection);
  const setGuessRejection = useStore((s) => s.game.setGuessRejection);

  const [inputValue, setInputValue] = useState('');
  const [selectedAirport, setSelectedAirport] = useState<Airport | null>(null);
  const [hasGuessed, setHasGuessed] = useState(false);
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    if (round && round.state === 'guessing') {
      setVisible(true);
      setInputValue('');
      setSelectedAirport(null);
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

  // The server recorded nothing for a refused guess, so the player can fix it and send again
  useEffect(() => {
    if (!guessRejection) return;
    setHasGuessed(false);
    setError(guessRejection.message);
  }, [guessRejection]);

  const disabled = hasGuessed || status !== 'connected';

  const submit = useCallback(() => {
    // Use selected airport code if available, otherwise use direct input
    let airportCode: string;

    if (selectedAirport) {
      // Prefer IATA code if available, otherwise use ICAO
      airportCode = selectedAirport.iata || selectedAirport.icao;
    } else {
      // Allow direct input of airport codes
      const trimmed = inputValue.trim().toUpperCase();
      if (!trimmed) {
        setError('Please select or enter an airport code');
        return;
      }
      const unknownCodeError = guessCodeError(trimmed);
      if (unknownCodeError) {
        setError(unknownCodeError);
        return;
      }
      airportCode = trimmed;
    }

    try {
      setGuessRejection(null);
      webSocketClient.send({ type: 'guess', payload: { airport_code: airportCode } });
      setHasGuessed(true);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [selectedAirport, inputValue, setGuessRejection]);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (disabled) return;
    submit();
  };

  const dismiss = () => {
    if (!hasGuessed) setVisible(false);
  };

  return {
    inputValue,
    selectedAirport,
    disabled,
    error,
    remaining,
    visible,
    setInputValue,
    setSelectedAirport,
    handleSubmit,
    dismiss,
  };
}
