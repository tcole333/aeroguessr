import { useState } from 'react';
import { useStore } from '../../../hooks/useStore';
import { createRoomAPI } from '../../../services/apiService';
import {
  selectFormError,
  selectIsLoading,
} from '../../ui/selectors';

export default function CreateRoomForm(): JSX.Element {
  const formError = useStore(selectFormError);
  const isLoading = useStore(selectIsLoading);
  const { setLoading, clearFormError, setFormError, setCurrentView } = useStore(
    (s) => s.ui,
  );
  const { setConnectionDetails } = useStore((s) => s.connection);

  const [nickname, setNickname] = useState('');
  const [mode, setMode] = useState<'Exact' | 'Distance'>('Exact');
  const [timeout, setTimeout] = useState(30);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    clearFormError();
    setLoading(true);
    try {
      const resp = await createRoomAPI({
        host_nickname: nickname,
        mode,
        round_timeout_seconds: timeout,
      });
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
      <h2 className="text-lg font-bold">Create Room</h2>
      <div>
        <label htmlFor="create-nick" className="block text-sm">Nickname</label>
        <input
          id="create-nick"
          className="border p-1 w-full"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          required
        />
      </div>
      <div>
        <label htmlFor="create-mode" className="block text-sm">Mode</label>
        <select
          id="create-mode"
          className="border p-1 w-full"
          value={mode}
          onChange={(e) => setMode(e.target.value as 'Exact' | 'Distance')}
        >
          <option value="Exact">Exact</option>
          <option value="Distance">Distance</option>
        </select>
      </div>
      <div>
        <label htmlFor="create-timeout" className="block text-sm">Round Timeout</label>
        <input
          id="create-timeout"
          type="number"
          className="border p-1 w-full"
          value={timeout}
          min={10}
          max={120}
          onChange={(e) => setTimeout(Number(e.target.value))}
        />
      </div>
      {formError && <p className="text-red-500">{formError}</p>}
      <button type="submit" disabled={isLoading} className="bg-blue-500 text-white px-2 py-1">
        Create
      </button>
    </form>
  );
}
