import { useState } from 'react';
import { useStore } from '../../../hooks/useStore';
import { startSoloGameAPI } from '../../../services/apiService';
import {
  selectFormError,
  selectIsLoading,
} from '../../ui/selectors';

export default function StartSoloForm(): JSX.Element {
  const formError = useStore(selectFormError);
  const isLoading = useStore(selectIsLoading);
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
