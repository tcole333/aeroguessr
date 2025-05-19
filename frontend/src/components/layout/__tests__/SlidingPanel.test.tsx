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
  it('shows plane list placeholder and switches tabs', async () => {
    renderPanel();
    expect(
      screen.getByText(/scanning for nearby flights/i),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: /leaderboard/i }));
    expect(screen.getByText(/no players yet/i)).toBeInTheDocument();
  });
});
