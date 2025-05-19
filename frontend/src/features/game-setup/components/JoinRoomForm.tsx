import { useState } from 'react';
import { useStore } from '../../../hooks/useStore';
import { joinRoomAPI } from '../../../services/apiService';
import {
  selectFormError,
  selectIsLoading,
} from '../../ui/selectors';

export default function JoinRoomForm(): JSX.Element {
  const formError = useStore(selectFormError);
  const isLoading = useStore(selectIsLoading);
  const { setLoading, clearFormError, setFormError, setCurrentView } = useStore(
    (s) => s.ui,
  );
  const { setConnectionDetails } = useStore((s) => s.connection);

  const [roomCode, setRoomCode] = useState('');
  const [nickname, setNickname] = useState('');

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    clearFormError();
    setLoading(true);
    try {
      const resp = await joinRoomAPI(roomCode.toUpperCase(), { nickname });
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
      <h2 className="text-lg font-bold">Join Room</h2>
      <div>
        <label htmlFor="join-code" className="block text-sm">Room Code</label>
        <input
          id="join-code"
          className="border p-1 w-full uppercase"
          value={roomCode}
          onChange={(e) => setRoomCode(e.target.value)}
          required
          minLength={4}
          maxLength={4}
        />
      </div>
      <div>
        <label htmlFor="join-nick" className="block text-sm">Nickname</label>
        <input
          id="join-nick"
          className="border p-1 w-full"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          required
        />
      </div>
      {formError && <p className="text-red-500">{formError}</p>}
      <button type="submit" disabled={isLoading} className="bg-blue-500 text-white px-2 py-1">
        Join
      </button>
    </form>
  );
}
