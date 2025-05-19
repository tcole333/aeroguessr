import { useState } from 'react';
import CreateRoomForm from '../features/game-setup/components/CreateRoomForm';
import JoinRoomForm from '../features/game-setup/components/JoinRoomForm';
import StartSoloForm from '../features/game-setup/components/StartSoloForm';

export default function HomePage(): JSX.Element {
  const [active, setActive] = useState<'create' | 'join' | 'solo' | null>(null);

  return (
    <div className="p-4 space-y-6 max-w-md mx-auto">
      <h1 className="text-3xl font-bold text-center">Plane Guessing Game</h1>
      <p className="text-center text-gray-600 dark:text-gray-300">
        Guess where flights are headed. Play solo or with friends!
      </p>
      <div className="space-y-4">
        <section>
          <button
            type="button"
            onClick={() => setActive(active === 'create' ? null : 'create')}
            className="w-full bg-blue-500 text-white px-4 py-2 rounded"
          >
            Create Room
          </button>
          {active === 'create' && (
            <div className="mt-2">
              <CreateRoomForm />
            </div>
          )}
        </section>
        <section>
          <button
            type="button"
            onClick={() => setActive(active === 'join' ? null : 'join')}
            className="w-full bg-blue-500 text-white px-4 py-2 rounded"
          >
            Join Room
          </button>
          {active === 'join' && (
            <div className="mt-2">
              <JoinRoomForm />
            </div>
          )}
        </section>
        <section>
          <button
            type="button"
            onClick={() => setActive(active === 'solo' ? null : 'solo')}
            className="w-full bg-blue-500 text-white px-4 py-2 rounded"
          >
            Start Solo
          </button>
          {active === 'solo' && (
            <div className="mt-2">
              <StartSoloForm />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
