import { render } from '@testing-library/react';
import { vi } from 'vitest';
import { InnerApp } from '../App';
import { StoreContext, createRootStore } from '../store/createRootStore';

// Mock the RoomCodeDisplay component
vi.mock('../components/ui/RoomCodeDisplay', () => ({
  RoomCodeDisplay: ({ className }: { className?: string }) => (
    <div className={className} data-testid="room-code-display">Room: TEST</div>
  ),
}));

describe('App view switching', () => {
  it('shows home when currentView=home', () => {
    const store = createRootStore();
    // Toggle retroMode off (default is true) to test standard mode UI
    store.getState().ui.toggleRetroMode();
    const { container } = render(
      <StoreContext.Provider value={store}>
        <InnerApp />
      </StoreContext.Provider>,
    );
    expect(container.textContent).toMatch(/plane guessing game/i);
  });

  it('shows game when view is game', () => {
    const store = createRootStore();
    // Toggle retroMode off (default is true) to test standard mode UI
    store.getState().ui.toggleRetroMode();
    store.getState().ui.setCurrentView('game');
    const { container } = render(
      <StoreContext.Provider value={store}>
        <InnerApp />
      </StoreContext.Provider>,
    );
    expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
  });
});
