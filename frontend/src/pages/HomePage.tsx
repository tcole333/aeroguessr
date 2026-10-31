import { useState, useEffect } from 'react';
import CreateRoomForm from '../features/game-setup/components/CreateRoomForm';
import JoinRoomForm from '../features/game-setup/components/JoinRoomForm';
import StartSoloForm from '../features/game-setup/components/StartSoloForm';
import { useStore } from '../hooks/useStore';
import { selectRetroMode } from '../features/ui/selectors';

export default function HomePage(): JSX.Element {
  const [active, setActive] = useState<'create' | 'join' | 'solo' | null>(null);
  const isRejoinAttempt = useStore((s) => s.connection.isRejoinAttempt);
  const connectionError = useStore((s) => s.connection.error);
  const retroMode = useStore(selectRetroMode);

  // Clock for retro mode
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    if (!retroMode) return;
    const interval = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, [retroMode]);

  // Retro-themed homepage
  if (retroMode) {
    return (
      <div className="retro min-h-screen bg-retro-bg flex items-center justify-center p-4">
        <div className="w-full max-w-xl">
          <div className="bg-retro-panel border border-retro-border shadow-[0_4px_16px_rgba(45,42,36,0.08)]">
            <div className="bg-retro-panel-dark border-b border-retro-border px-6 py-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-display uppercase tracking-[0.3em] text-retro-text-muted">
                    Departure Board
                  </p>
                  <h1 className="mt-2 font-splitflap text-2xl tracking-[0.12em] text-retro-primary drop-shadow-[0_0_8px_rgba(187,104,48,0.5)]">
                    ROUTE LEDGER
                  </h1>
                  <p className="mt-1 text-sm font-display text-retro-text-muted uppercase tracking-wider">
                    Select a gate to begin
                  </p>
                </div>
                <div className="text-right">
                  <div className="font-splitflap text-lg text-retro-led">
                    {time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })}
                  </div>
                  <div className="text-xs font-display uppercase tracking-wider text-retro-text-muted">
                    Local Time
                  </div>
                </div>
              </div>
            </div>

            <div className="p-6 space-y-5">
              {/* Rejoin status */}
              {isRejoinAttempt && (
                <div className="p-3 bg-retro-panel-dark border border-retro-primary text-center">
                  <p className="font-display text-sm text-retro-primary uppercase tracking-wider">
                    Reconnecting to previous session...
                  </p>
                </div>
              )}

              {/* Connection error */}
              {connectionError && (
                <div className="p-3 bg-retro-panel-dark border border-retro-accent text-center">
                  <p className="font-display text-sm text-retro-accent">{connectionError}</p>
                </div>
              )}

              {/* Action buttons */}
              <div className="space-y-3">
                {/* Create Room */}
                <div>
                  <button
                    type="button"
                    onClick={() => setActive(active === 'create' ? null : 'create')}
                    className={`w-full py-3 px-4 font-display text-sm uppercase tracking-widest border-2 transition-all ${
                      active === 'create'
                        ? 'bg-retro-primary text-retro-panel border-retro-primary'
                        : 'bg-retro-panel text-retro-primary border-retro-border hover:border-retro-primary'
                    }`}
                  >
                    Create Room
                  </button>
                  {active === 'create' && (
                    <div className="mt-3 p-4 bg-retro-panel-dark border border-retro-border">
                      <CreateRoomForm />
                    </div>
                  )}
                </div>

                {/* Join Room */}
                <div>
                  <button
                    type="button"
                    onClick={() => setActive(active === 'join' ? null : 'join')}
                    className={`w-full py-3 px-4 font-display text-sm uppercase tracking-widest border-2 transition-all ${
                      active === 'join'
                        ? 'bg-retro-primary text-retro-panel border-retro-primary'
                        : 'bg-retro-panel text-retro-primary border-retro-border hover:border-retro-primary'
                    }`}
                  >
                    Join Room
                  </button>
                  {active === 'join' && (
                    <div className="mt-3 p-4 bg-retro-panel-dark border border-retro-border">
                      <JoinRoomForm />
                    </div>
                  )}
                </div>

                {/* Solo */}
                <div>
                  <button
                    type="button"
                    onClick={() => setActive(active === 'solo' ? null : 'solo')}
                    className={`w-full py-3 px-4 font-display text-sm uppercase tracking-widest border-2 transition-all ${
                      active === 'solo'
                        ? 'bg-retro-primary text-retro-panel border-retro-primary'
                        : 'bg-retro-panel text-retro-text border-retro-border hover:border-retro-primary hover:text-retro-primary'
                    }`}
                  >
                    Solo Flight
                  </button>
                  {active === 'solo' && (
                    <div className="mt-3 p-4 bg-retro-panel-dark border border-retro-border">
                      <StartSoloForm />
                    </div>
                  )}
                </div>
              </div>

              {/* Footer */}
              <div className="pt-4 border-t border-retro-border text-center">
                <p className="font-display text-xs text-retro-text-muted uppercase tracking-wider">
                  Choose a room to begin your flight.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Original homepage
  return (
    <div className="p-4 space-y-6 max-w-md mx-auto relative">
      <h1 className="text-3xl font-bold text-center">AeroGuessr</h1>
      <p className="text-center text-gray-600 dark:text-gray-300">
        Guess where flights are headed. Play solo or with friends!
      </p>

      {/* Show rejoin status */}
      {isRejoinAttempt && (
        <div className="p-4 bg-blue-100 border border-blue-300 rounded text-center">
          <p className="text-blue-800">Attempting to rejoin your previous session...</p>
        </div>
      )}

      {/* Show connection error */}
      {connectionError && (
        <div className="p-4 bg-red-100 border border-red-300 rounded text-center">
          <p className="text-red-800">{connectionError}</p>
        </div>
      )}

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
