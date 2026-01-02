import { useState } from 'react';
import { useStore } from '../../../hooks/useStore';
import { startSoloGameAPI } from '../../../services/apiService';
import {
  selectFormError,
  selectIsLoading,
  selectRetroMode,
} from '../../ui/selectors';

export default function StartSoloForm(): JSX.Element {
  const formError = useStore(selectFormError);
  const isLoading = useStore(selectIsLoading);
  const retroMode = useStore(selectRetroMode);
  const { setLoading, clearFormError, setFormError, setCurrentView } = useStore(
    (s) => s.ui,
  );
  const { setConnectionDetails } = useStore((s) => s.connection);

  const [nickname, setNickname] = useState('');

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    clearFormError();
    setLoading(true);
    try {
      const resp = await startSoloGameAPI({ nickname });
      setConnectionDetails({
        roomCode: resp.room_code,
        wsUrl: resp.ws_url,
        nickname,
      });
      setCurrentView('game');
    } catch (err: unknown) {
      setFormError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (retroMode) {
    return (
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="solo-nick" className="block font-display text-xs text-retro-text-muted uppercase tracking-wider mb-1">
            Nickname
          </label>
          <input
            id="solo-nick"
            className="w-full bg-retro-panel border border-retro-border p-2 font-splitflap text-retro-led uppercase tracking-wider focus:border-retro-primary focus:outline-none"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            required
            placeholder="Enter name"
          />
        </div>
        {formError && <p className="font-display text-sm text-retro-accent">{formError}</p>}
        <button
          type="submit"
          disabled={isLoading}
          className="w-full py-2 px-4 font-display text-sm uppercase tracking-widest bg-retro-primary text-retro-panel border-0 hover:bg-retro-primary-bright transition-colors disabled:opacity-50"
        >
          {isLoading ? 'Starting...' : 'Start'}
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <h2 className="text-lg font-bold">Start Solo</h2>
      <div>
        <label htmlFor="solo-nick" className="block text-sm">Nickname</label>
        <input
          id="solo-nick"
          className="border p-1 w-full"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          required
        />
      </div>
      {formError && <p className="text-red-500">{formError}</p>}
      <button type="submit" disabled={isLoading} className="bg-blue-500 text-white px-2 py-1">
        Start
      </button>
    </form>
  );
}
