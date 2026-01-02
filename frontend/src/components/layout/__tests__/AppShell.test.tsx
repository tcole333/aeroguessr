import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import AppShell from '../AppShell';
import { StoreContext, createRootStore } from '../../../store/createRootStore';

// Mock the RoomCodeDisplay component
vi.mock('../../ui/RoomCodeDisplay', () => ({
  RoomCodeDisplay: ({ className }: { className?: string }) => (
    <div className={className} data-testid="room-code-display">Room: TEST</div>
  ),
}));

function renderAppShell() {
  const store = createRootStore();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();
  return render(
    <StoreContext.Provider value={store}>
      <AppShell />
    </StoreContext.Provider>,
  );
}

describe('AppShell', () => {
  it('renders map and panel', () => {
    const { container, getByRole } = renderAppShell();
    expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
    expect(getByRole('tablist')).toBeInTheDocument();
  });

  it('keeps map flex-1 and shrinks panel on toggle', async () => {
    const { container } = renderAppShell();
    const toggle = screen.getByRole('button', { name: /minimize panel/i });
    const rootDiv = container.firstElementChild as HTMLElement;
    const panelDiv = rootDiv.lastElementChild as HTMLElement;
    const mapDiv = rootDiv.firstElementChild as HTMLElement;
    expect(mapDiv).toHaveClass('flex-1');
    await userEvent.click(toggle);
    expect(panelDiv).toHaveClass('md:w-16');
    expect(mapDiv).toHaveClass('flex-1');
  });
});
