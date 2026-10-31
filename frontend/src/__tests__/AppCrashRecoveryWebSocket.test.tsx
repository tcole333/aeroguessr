import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { WebSocketClient } from '../lib/WebSocketClient';
import { FakeWebSocket } from '../mocks/fakeWebSocket';

// The game view crashes on its first render, before it has opened a socket.
vi.mock('../components/layout/AppShell', () => ({
  default: function CrashingAppShell(): JSX.Element {
    throw new TypeError('round result crashed');
  },
}));

/**
 * Loads the app with a saved session for room ABCD, lets the game view crash on
 * its first render, and picks "Back to home". The reload is stubbed, so the
 * returned client is the one the crashed page used. Modules are reset so each
 * test starts with a fresh client.
 */
async function crashInRoomThenGoHome(): Promise<WebSocketClient> {
  vi.resetModules();
  const { createRootStore, StoreProvider } = await import('../store/createRootStore');
  const { InnerApp } = await import('../App');
  const { AppErrorBoundary } = await import('../components/ErrorBoundary/AppErrorBoundary');
  const { CrashRecoveryScreen } = await import('../components/ErrorBoundary/CrashRecoveryScreen');
  const { webSocketClient } = await import('../hooks/useWebSocketManager');

  const previousPage = createRootStore().getState();
  previousPage.connection.setConnectionDetails({
    roomCode: 'ABCD',
    wsUrl: 'ws://localhost/api/v0/rooms/ws/ABCD/Ann',
    nickname: 'Ann',
  });
  previousPage.ui.setCurrentView('game');

  render(
    <StoreProvider>
      <AppErrorBoundary renderFallback={(error) => <CrashRecoveryScreen error={error} onReload={vi.fn()} />}>
        <InnerApp />
      </AppErrorBoundary>
    </StoreProvider>,
  );
  await userEvent.click(screen.getByRole('button', { name: 'Back to home' }));
  return webSocketClient;
}

function joinRoom(client: WebSocketClient): FakeWebSocket {
  client.connect('WXYZ', 'Ann');
  const socket = FakeWebSocket.latest();
  socket.serverAccepts();
  return socket;
}

describe('"Back to home" after the game view crashes before connecting', () => {
  beforeEach(() => {
    localStorage.clear();
    FakeWebSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('does not replay a leave into the next room the player joins', async () => {
    const client = await crashInRoomThenGoHome();

    const socket = joinRoom(client);

    expect(socket.sentTypes()).not.toContain('leave');
  });

  it('leaves the next room able to reconnect after a dropped connection', async () => {
    const client = await crashInRoomThenGoHome();
    vi.useFakeTimers();
    const socket = joinRoom(client);

    socket.serverCloses();
    vi.advanceTimersByTime(1000);

    expect(FakeWebSocket.latest()).not.toBe(socket);
  });
});
