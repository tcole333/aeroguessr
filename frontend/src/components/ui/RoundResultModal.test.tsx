import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RoundResultModal } from './RoundResultModal';
import { createRootStore } from '../../store/createRootStore';
import { StoreContext } from '../../store/createRootStore';

describe('RoundResultModal', () => {
  let store: ReturnType<typeof createRootStore>;

  beforeEach(() => {
    store = createRootStore();
  });

  const renderWithStore = (component: React.ReactElement) => {
    return render(
      <StoreContext.Provider value={store}>
        {component}
      </StoreContext.Provider>
    );
  };

  it('should not render when no round result', () => {
    const { container } = renderWithStore(<RoundResultModal />);
    expect(container.firstChild).toBeNull();
  });

  it('should render when round result is set', () => {
    // Set up round result
    store.getState().game.lastRoundResult = {
      results: [
        {
          nickname: 'Player1',
          guess: 'JFK',
          correct_code: 'BOS',
          score_awarded: 0,
          current_total_score: 100,
        },
        {
          nickname: 'Player2',
          guess: 'BOS',
          correct_code: 'BOS',
          score_awarded: 100,
          current_total_score: 250,
        },
      ],
      next_host_nickname: null,
    };

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText('Round Complete!')).toBeInTheDocument();
    expect(screen.getByText('BOS')).toBeInTheDocument();
    expect(screen.getByText('Player1')).toBeInTheDocument();
    expect(screen.getByText('Player2')).toBeInTheDocument();
  });

  it('should sort results by score awarded', () => {
    store.getState().game.lastRoundResult = {
      results: [
        {
          nickname: 'LowScorer',
          guess: 'LAX',
          correct_code: 'BOS',
          score_awarded: 0,
          current_total_score: 50,
        },
        {
          nickname: 'HighScorer',
          guess: 'BOS',
          correct_code: 'BOS',
          score_awarded: 100,
          current_total_score: 300,
        },
        {
          nickname: 'MidScorer',
          guess: 'JFK',
          correct_code: 'BOS',
          score_awarded: 50,
          current_total_score: 150,
        },
      ],
      next_host_nickname: null,
    };

    renderWithStore(<RoundResultModal />);

    const nicknames = screen.getAllByText(/Scorer/).map(el => el.textContent);
    expect(nicknames[0]).toContain('HighScorer');
    expect(nicknames[1]).toContain('MidScorer');
    expect(nicknames[2]).toContain('LowScorer');
  });

  it('should highlight current player result', () => {
    store.getState().connection.nickname = 'MyNickname';
    store.getState().game.lastRoundResult = {
      results: [
        {
          nickname: 'OtherPlayer',
          guess: 'JFK',
          correct_code: 'BOS',
          score_awarded: 0,
          current_total_score: 100,
        },
        {
          nickname: 'MyNickname',
          guess: 'BOS',
          correct_code: 'BOS',
          score_awarded: 100,
          current_total_score: 250,
        },
      ],
      next_host_nickname: null,
    };

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText('(You)')).toBeInTheDocument();
  });

  it('should close modal on button click', async () => {
    const user = userEvent.setup();
    store.getState().game.lastRoundResult = {
      results: [
        {
          nickname: 'Player1',
          guess: 'BOS',
          correct_code: 'BOS',
          score_awarded: 100,
          current_total_score: 100,
        },
      ],
      next_host_nickname: null,
    };

    renderWithStore(<RoundResultModal />);
    const continueButton = screen.getByRole('button', { name: /Close round results/i });

    await user.click(continueButton);

    // Wait for animation to complete - check document body since we're using a portal
    await waitFor(() => {
      expect(document.body.querySelector('.opacity-0')).toBeInTheDocument();
    });
  });

  it.skip('should auto-close after delay', async () => {
    vi.useFakeTimers();

    store.getState().game.lastRoundResult = {
      results: [
        {
          nickname: 'Player1',
          guess: 'BOS',
          correct_code: 'BOS',
          score_awarded: 100,
          current_total_score: 100,
        },
      ],
      next_host_nickname: null,
    };

    const { container } = renderWithStore(<RoundResultModal autoCloseDelay={1000} />);

    expect(screen.getByText('Round Complete!')).toBeInTheDocument();

    // Fast-forward time and wait for close animation
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    // Wait for closing state
    await waitFor(() => {
      expect(container.querySelector('.opacity-0')).toBeInTheDocument();
    }, { timeout: 1000 });

    vi.useRealTimers();
  });

  it('should show distance mode hint for non-perfect scores', () => {
    store.getState().connection.nickname = 'MyNickname';
    store.getState().game.scoringMode = 'Distance';
    store.getState().game.lastRoundResult = {
      results: [
        {
          nickname: 'MyNickname',
          guess: 'JFK',
          correct_code: 'BOS',
          score_awarded: 75,
          current_total_score: 175,
        },
      ],
      next_host_nickname: null,
    };

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText(/In Distance mode/)).toBeInTheDocument();
  });

  it('should not show distance mode hint for exact mode', () => {
    store.getState().connection.nickname = 'MyNickname';
    store.getState().game.scoringMode = 'Exact';
    store.getState().game.lastRoundResult = {
      results: [
        {
          nickname: 'MyNickname',
          guess: 'JFK',
          correct_code: 'BOS',
          score_awarded: 0,
          current_total_score: 100,
        },
      ],
      next_host_nickname: null,
    };

    renderWithStore(<RoundResultModal />);

    expect(screen.queryByText(/In Distance mode/)).not.toBeInTheDocument();
  });
});
