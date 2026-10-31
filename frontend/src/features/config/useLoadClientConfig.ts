import { useEffect } from 'react';
import { useStore } from '../../hooks/useStore';
import { selectLoadClientConfig } from './selectors';

/**
 * Loads the client config when the calling component mounts, unless it is loaded or
 * loading already. The app calls it at startup; the map calls it too, which retries a
 * startup load that failed.
 */
export function useLoadClientConfig(): void {
  const loadClientConfig = useStore(selectLoadClientConfig);

  useEffect(() => {
    void loadClientConfig();
  }, [loadClientConfig]);
}
