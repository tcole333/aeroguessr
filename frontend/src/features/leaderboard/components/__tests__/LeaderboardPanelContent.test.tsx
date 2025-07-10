import { render, screen } from '@testing-library/react';
import { act } from 'react';
import LeaderboardPanelContent from '../LeaderboardPanelContent';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';

describe('LeaderboardPanelContent', () => {
  function setup(initialScores: Record<string, number>, hostNickname?: string) {
    const store = createRootStore();
    store.getState().game.applyDelta({ scores: initialScores });
    store.getState().connection.setNickname('Bob');
    if (hostNickname) {
      store.getState().game.setHostNickname(hostNickname);
    }
    return { store, ...render(
      <StoreContext.Provider value={store}>
        <LeaderboardPanelContent />
      </StoreContext.Provider>,
    )};
  }

  it('renders sorted scores', () => {
    setup({ Alice: 10, Bob: 20 });
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Bob');
    expect(items[1]).toHaveTextContent('Alice');
  });

  it('shows confetti on leader change', () => {
    const { store } = setup({ Alice: 10 });
    expect(screen.queryByTestId('confetti')).not.toBeInTheDocument();
    act(() => {
      store.getState().game.applyDelta({ scores: { Bob: 20, Alice: 10 } });
    });
    expect(screen.getByTestId('confetti')).toBeInTheDocument();
  });

  it('shows placeholder when no players', () => {
    setup({});
    expect(screen.getByText(/no players yet/i)).toBeInTheDocument();
  });

  it('highlights current player', () => {
    setup({ Bob: 15, Alice: 10 });
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveClass('font-bold');
  });

  it('renders without highlight when nickname null', () => {
    const { store } = setup({ Bob: 15 });
    act(() => {
      store.getState().connection.setNickname(null);
    });
    const item = screen.getByRole('listitem');
    expect(item).not.toHaveClass('font-bold');
  });

  describe('host indicators', () => {
    it('shows crown icon for host player', () => {
      setup({ Alice: 10, Bob: 20 }, 'Bob');

      const hostIndicator = screen.getByRole('status', { name: 'Host player' });
      expect(hostIndicator).toBeInTheDocument();
      expect(hostIndicator).toHaveTextContent('Host');

      // Verify it's next to Bob's name
      const bobItem = screen.getByText('Bob').closest('li');
      expect(bobItem).toContainElement(hostIndicator);
    });

    it('does not show crown for non-host players', () => {
      setup({ Alice: 10, Bob: 20 }, 'Bob');

      // Alice should not have a crown
      const aliceItem = screen.getByText('Alice').closest('li');
      expect(aliceItem).not.toContainElement(
        screen.getByRole('status', { name: 'Host player' })
      );
    });

    it('updates host indicator when host changes', () => {
      const { store } = setup({ Alice: 10, Bob: 20 }, 'Alice');

      // Initially Alice is host
      let aliceItem = screen.getByText('Alice').closest('li');
      expect(aliceItem).toContainElement(
        screen.getByRole('status', { name: 'Host player' })
      );

      // Change host to Bob
      act(() => {
        store.getState().game.setHostNickname('Bob');
      });

      // Now Bob should have the crown
      const bobItem = screen.getByText('Bob').closest('li');
      expect(bobItem).toContainElement(
        screen.getByRole('status', { name: 'Host player' })
      );

      // Alice should no longer have it
      aliceItem = screen.getByText('Alice').closest('li');
      const indicators = screen.getAllByRole('status', { name: 'Host player' });
      expect(indicators).toHaveLength(1); // Only one host indicator
    });

    it('removes host indicator when host becomes null', () => {
      const { store } = setup({ Alice: 10, Bob: 20 }, 'Bob');

      // Initially Bob is host
      expect(screen.getByRole('status', { name: 'Host player' })).toBeInTheDocument();

      // Remove host
      act(() => {
        store.getState().game.setHostNickname(null);
      });

      // No host indicators should exist
      expect(screen.queryByRole('status', { name: 'Host player' })).not.toBeInTheDocument();
    });
  });
});
