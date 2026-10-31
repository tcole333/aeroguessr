import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { vi } from 'vitest';
import AppShell from '../AppShell';
import { StoreContext } from '../../../store/createRootStore';
import { createStoreWithClientConfig } from '../../../mocks/configuredStore';

// Mock the RoomCodeDisplay component
vi.mock('../../ui/RoomCodeDisplay', () => ({
  RoomCodeDisplay: ({ className }: { className?: string }) => (
    <div className={className} data-testid="room-code-display">Room: TEST</div>
  ),
}));

async function renderAppShell() {
  const store = await createStoreWithClientConfig();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();
  return render(
    <StoreContext.Provider value={store}>
      <AppShell />
    </StoreContext.Provider>,
  );
}

describe('AppShell', () => {
  it('renders map and panel', async () => {
    const { container, getByRole } = await renderAppShell();
    expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
    expect(getByRole('tablist')).toBeInTheDocument();
  });

  it('keeps map flex-1 and shrinks panel on toggle', async () => {
    const { container } = await renderAppShell();
    const toggle = screen.getByRole('button', { name: /minimize panel/i });
    const rootDiv = container.firstElementChild as HTMLElement;
    const panelDiv = rootDiv.lastElementChild as HTMLElement;
    const mapDiv = rootDiv.firstElementChild as HTMLElement;
    expect(mapDiv).toHaveClass('flex-1');
    await userEvent.click(toggle);
    expect(panelDiv).toHaveClass('md:w-16');
    expect(mapDiv).toHaveClass('flex-1');
  });

  it('mounts the toaster that shows server errors', async () => {
    await renderAppShell();

    act(() => {
      toast.error('Only the host can start the round.');
    });

    expect(await screen.findByText('Only the host can start the round.')).toBeInTheDocument();
  });
});
