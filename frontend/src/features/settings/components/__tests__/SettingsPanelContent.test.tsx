import { render, screen } from '@testing-library/react';
import { act } from 'react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import SettingsPanelContent from '../SettingsPanelContent';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';

// Mock the WebSocket client
vi.mock('../../../../hooks/useWebSocketManager', () => ({
  webSocketClient: {
    send: vi.fn(),
    destroy: vi.fn(),
  },
}));

function setup({ darkMode = false } = {}) {
  const store = createRootStore();
  if (darkMode) {
    store.getState().ui.toggleDarkMode();
  }
  return { store, ...render(
    <StoreContext.Provider value={store}>
      <SettingsPanelContent />
    </StoreContext.Provider>,
  )};
}

describe('SettingsPanelContent', () => {
  it('toggles night mode', async () => {
    const { store } = setup();
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();
    await userEvent.click(checkbox);
    expect(store.getState().ui.darkMode).toBe(true);
  });

  it('handles leave room action', async () => {
    const { store } = setup();
    const { webSocketClient } = await import('../../../../hooks/useWebSocketManager');

    // Set up some initial connection state
    store.getState().connection.setConnectionDetails({
      roomCode: 'TEST',
      wsUrl: 'ws://localhost:8000/ws/TEST/TestPlayer',
      nickname: 'TestPlayer'
    });
    store.getState().ui.setCurrentView('game');

    await userEvent.click(screen.getByRole('button', { name: /leave room/i }));

    // Verify WebSocket leave message was sent
    expect(webSocketClient.send).toHaveBeenCalledWith({ type: 'leave', payload: {} });

    // Verify WebSocket connection was destroyed
    expect(webSocketClient.destroy).toHaveBeenCalled();

    // Verify state was cleared and view returned to home
    expect(store.getState().connection.nickname).toBeNull();
    expect(store.getState().ui.currentView).toBe('home');
  });


});
