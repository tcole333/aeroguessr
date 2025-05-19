import { render, screen } from '@testing-library/react';
import { act } from 'react';
import LeaderboardPanelContent from '../LeaderboardPanelContent';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';

describe('LeaderboardPanelContent', () => {
  function setup(initialScores: Record<string, number>) {
    const store = createRootStore();
    store.getState().game.applyDelta({ scores: initialScores });
    store.getState().connection.setNickname('Bob');
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
});
