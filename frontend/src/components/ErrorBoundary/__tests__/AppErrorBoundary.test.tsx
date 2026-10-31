import { render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';
import { AppErrorBoundary } from '../AppErrorBoundary';
import { CrashRecoveryScreen } from '../CrashRecoveryScreen';
import { StoreContext, createRootStore, type RootStore } from '../../../store/createRootStore';
import { useStore } from '../../../hooks/useStore';
import { useAutoRejoin } from '../../../hooks/useAutoRejoin';

/** Crashes while the player is in the game view, like a broken round result would. */
function CrashesInGame(): JSX.Element {
  const currentView = useStore((s) => s.ui.currentView);
  if (currentView === 'game') {
    throw new TypeError('boom');
  }
  return <p>Home page</p>;
}

function AlwaysCrashes(): JSX.Element {
  throw new TypeError('boom');
}

interface Session {
  roomCode: string;
  wsUrl: string;
  nickname: string;
}

function createStore({
  session,
  view = 'game',
  darkMode = false,
}: { session?: Session; view?: 'home' | 'game'; darkMode?: boolean } = {}): RootStore {
  const store = createRootStore();
  if (session) {
    store.getState().connection.setConnectionDetails(session);
  }
  store.getState().ui.setCurrentView(view);
  if (darkMode) {
    store.getState().ui.toggleDarkMode();
  }
  return store;
}

function renderApp(store: RootStore, child: JSX.Element, onReload = vi.fn()) {
  render(
    <StoreContext.Provider value={store}>
      <AppErrorBoundary renderFallback={(error) => <CrashRecoveryScreen error={error} onReload={onReload} />}>
        {child}
      </AppErrorBoundary>
    </StoreContext.Provider>,
  );
  return { onReload };
}

const roomSession: Session = {
  roomCode: 'ABCD',
  wsUrl: 'ws://localhost:8000/api/v0/rooms/ws/ABCD/Ann',
  nickname: 'Ann',
};

describe('AppErrorBoundary with CrashRecoveryScreen', () => {
  let consoleError: MockInstance;

  beforeEach(() => {
    // createRootStore rehydrates the persisted session; start every test without one.
    localStorage.clear();
    // React and jsdom both report the caught render error; keep test output readable.
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleError.mockRestore();
  });

  it('shows a recovery screen instead of a blank page when a child throws', () => {
    renderApp(createStore({ session: roomSession }), <CrashesInGame />);

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
  });

  it('logs the error name, message and stack as one readable string', () => {
    renderApp(createStore({ session: roomSession }), <CrashesInGame />);

    const report = consoleError.mock.calls
      .map(([first]) => first)
      .find((first): first is string => typeof first === 'string' && first.startsWith('[AppErrorBoundary]'));
    expect(report).toContain('TypeError: boom');
    expect(report).toContain('at CrashesInGame');
    expect(report).toContain('Component stack:');
  });

  it('offers to rejoin the room and reloads when chosen', async () => {
    const { onReload } = renderApp(createStore({ session: roomSession }), <CrashesInGame />);

    await userEvent.click(screen.getByRole('button', { name: 'Rejoin room ABCD' }));

    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it('keeps the session so the page loaded after "Rejoin" rejoins the same room', async () => {
    renderApp(createStore({ session: roomSession }), <CrashesInGame />);

    await userEvent.click(screen.getByRole('button', { name: 'Rejoin room ABCD' }));

    const reloaded = createRootStore();
    renderHook(() => useAutoRejoin(), {
      wrapper: ({ children }) => <StoreContext.Provider value={reloaded}>{children}</StoreContext.Provider>,
    });
    const { isRejoinAttempt, roomCode, wsUrl } = reloaded.getState().connection;
    expect({ isRejoinAttempt, roomCode, wsUrl }).toEqual({
      isRejoinAttempt: true,
      roomCode: 'ABCD',
      wsUrl: roomSession.wsUrl,
    });
  });

  it('offers only "Back to home" for a solo game, which the server ends when its socket closes', () => {
    const soloSession = { ...roomSession, roomCode: 'solo:1a2b3c4d' };
    renderApp(createStore({ session: soloSession }), <CrashesInGame />);

    const actions = screen.getAllByRole('button').map((button) => button.textContent);
    expect(actions).toEqual(['Back to home']);
  });

  it.each([
    ['there is no saved session', createStore],
    ['the player was not in the game view', () => createStore({ session: roomSession, view: 'home' })],
  ])('offers a plain reload when %s', (_case, makeStore) => {
    renderApp(makeStore(), <AlwaysCrashes />);

    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it('reloads from "Back to home"', async () => {
    const { onReload } = renderApp(createStore({ session: roomSession }), <CrashesInGame />);

    await userEvent.click(screen.getByRole('button', { name: 'Back to home' }));

    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it('starts the page loaded after "Back to home" on the home screen without the room', async () => {
    renderApp(createStore({ session: roomSession }), <CrashesInGame />);

    await userEvent.click(screen.getByRole('button', { name: 'Back to home' }));

    const reloaded = createRootStore().getState();
    expect({ view: reloaded.ui.currentView, roomCode: reloaded.connection.roomCode }).toEqual({
      view: 'home',
      roomCode: null,
    });
  });

  it('keeps the same actions on screen while "Back to home" reloads the page', async () => {
    renderApp(createStore({ session: roomSession }), <CrashesInGame />);

    await userEvent.click(screen.getByRole('button', { name: 'Back to home' }));

    const actions = screen.getAllByRole('button').map((button) => button.textContent);
    expect(actions).toEqual(['Rejoin room ABCD', 'Back to home']);
  });

  it('keeps the night mode preference across the reload from "Back to home"', async () => {
    renderApp(createStore({ session: roomSession, darkMode: true }), <CrashesInGame />);

    await userEvent.click(screen.getByRole('button', { name: 'Back to home' }));

    expect(createRootStore().getState().ui.darkMode).toBe(true);
  });

  it('keeps the dark theme when night mode is on', () => {
    renderApp(createStore({ session: roomSession, darkMode: true }), <CrashesInGame />);

    expect(screen.getByRole('alert').closest('.dark')).not.toBeNull();
  });
});
