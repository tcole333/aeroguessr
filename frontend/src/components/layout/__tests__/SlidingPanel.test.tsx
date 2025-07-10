import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import SlidingPanel from '../SlidingPanel';
import { StoreProvider } from '../../../store/createRootStore';

// Mock the RoomCodeDisplay component
vi.mock('../../ui/RoomCodeDisplay', () => ({
  RoomCodeDisplay: ({ className }: { className?: string }) => (
    <div className={className} data-testid="room-code-display">Room: TEST</div>
  ),
}));

function renderPanel() {
  return render(
    <StoreProvider>
      <SlidingPanel />
    </StoreProvider>,
  );
}

describe('SlidingPanel', () => {
  it('shows plane list placeholder and switches tabs', async () => {
    renderPanel();
    expect(
      screen.getByText(/scanning for nearby flights/i),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: /leaderboard/i }));
    expect(screen.getByText(/no players yet/i)).toBeInTheDocument();
  });

  it('toggles open and closed state', async () => {
    const { container } = renderPanel();
    const toggleBtn = screen.getByRole('button', { name: /minimize panel/i });
    expect(container.firstChild).toHaveClass('h-1/2');
    await userEvent.click(toggleBtn);
    expect(toggleBtn).toHaveAttribute('aria-expanded', 'false');
    expect(container.firstChild).toHaveClass('h-16');
    expect(container.firstChild).toHaveClass('md:w-16');
  });
});
