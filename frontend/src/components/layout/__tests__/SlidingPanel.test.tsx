import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SlidingPanel from '../SlidingPanel';
import { StoreProvider } from '../../../store/createRootStore';

function renderPanel() {
  return render(
    <StoreProvider>
      <SlidingPanel />
    </StoreProvider>,
  );
}

describe('SlidingPanel', () => {
  it('shows placeholder content and switches tabs', async () => {
    renderPanel();
    expect(screen.getByText(/Plane List Panel/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: /leaderboard/i }));
    expect(screen.getByText(/Leaderboard Panel/)).toBeInTheDocument();
  });
});
