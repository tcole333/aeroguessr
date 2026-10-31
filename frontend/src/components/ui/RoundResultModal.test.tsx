import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RoundResultModal } from './RoundResultModal';
import { createRootStore } from '../../store/createRootStore';
import { StoreContext } from '../../store/createRootStore';

describe('RoundResultModal', () => {
  let store: ReturnType<typeof createRootStore>;

  beforeEach(() => {
    store = createRootStore();
    // Toggle retroMode off (default is true) to test standard mode UI
    store.getState().ui.toggleRetroMode();
  });

  afterEach(() => {
    vi.useRealTimers();
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
    store.setState((s) => {
      s.game.lastRoundResult = {
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
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText('Round Complete!')).toBeInTheDocument();
    // BOS is displayed as friendly name "Boston" via formatAirportDisplay
    expect(screen.getByText('Boston')).toBeInTheDocument();
    expect(screen.getByText('Player1')).toBeInTheDocument();
    expect(screen.getByText('Player2')).toBeInTheDocument();
  });

  it('should sort results by score awarded', () => {
    store.setState((s) => {
      s.game.lastRoundResult = {
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
    });

    renderWithStore(<RoundResultModal />);

    const nicknames = screen.getAllByText(/Scorer/).map(el => el.textContent);
    expect(nicknames[0]).toContain('HighScorer');
    expect(nicknames[1]).toContain('MidScorer');
    expect(nicknames[2]).toContain('LowScorer');
  });

  it('should highlight current player result', () => {
    store.setState((s) => {
      s.connection.nickname = 'MyNickname';
      s.game.lastRoundResult = {
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
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText('(You)')).toBeInTheDocument();
  });

  it('should close modal on button click', async () => {
    const user = userEvent.setup();
    store.setState((s) => {
      s.game.lastRoundResult = {
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
    });

    renderWithStore(<RoundResultModal />);
    const continueButton = screen.getByRole('button', { name: /Close round results/i });

    await user.click(continueButton);

    // Wait for animation to complete - check document body since we're using a portal
    await waitFor(() => {
      expect(document.body.querySelector('.opacity-0')).toBeInTheDocument();
    });
  });

  it('should auto-close after delay', () => {
    vi.useFakeTimers();

    store.setState((s) => {
      s.game.lastRoundResult = {
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
    });

    renderWithStore(<RoundResultModal autoCloseDelay={1000} />);

    expect(screen.getByText('Round Complete!')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(999);
    });
    // Still fully shown: the close fade has not started early.
    expect(screen.getByText('Round Complete!')).toBeInTheDocument();
    expect(document.body.querySelector('.opacity-0')).toBeNull();

    // Once the delay elapses the close animation starts; flush it so the modal unmounts.
    // The modal is portaled to document.body, so query through screen rather than the container.
    act(() => {
      vi.advanceTimersByTime(1);
      vi.runOnlyPendingTimers();
    });
    expect(screen.queryByText('Round Complete!')).not.toBeInTheDocument();
  });

  it('should show distance mode hint for non-perfect scores', () => {
    store.setState((s) => {
      s.connection.nickname = 'MyNickname';
      s.game.scoringMode = 'Distance';
      s.game.lastRoundResult = {
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
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText(/In Distance mode/)).toBeInTheDocument();
  });

  it('should not show distance mode hint for exact mode', () => {
    store.setState((s) => {
      s.connection.nickname = 'MyNickname';
      s.game.scoringMode = 'Exact';
      s.game.lastRoundResult = {
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
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.queryByText(/In Distance mode/)).not.toBeInTheDocument();
  });

  it('should display distance in km for Distance mode', () => {
    store.setState((s) => {
      s.game.scoringMode = 'Distance';
      s.game.lastRoundResult = {
        results: [
          {
            nickname: 'Player1',
            guess: 'JFK',
            correct_code: 'BOS',
            score_awarded: 70,
            current_total_score: 170,
            distance_km: 305.5,
          },
          {
            nickname: 'Player2',
            guess: 'PVD',
            correct_code: 'BOS',
            score_awarded: 93,
            current_total_score: 193,
            distance_km: 70.2,
          },
        ],
        next_host_nickname: null,
      };
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText(/306 km away/)).toBeInTheDocument();
    expect(screen.getByText(/70 km away/)).toBeInTheDocument();
  });

  it('should display "Exact match!" for 0 km distance', () => {
    store.setState((s) => {
      s.game.scoringMode = 'Distance';
      s.game.lastRoundResult = {
        results: [
          {
            nickname: 'Player1',
            guess: 'BOS',
            correct_code: 'BOS',
            score_awarded: 100,
            current_total_score: 200,
            distance_km: 0,
          },
        ],
        next_host_nickname: null,
      };
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText(/Exact match!/)).toBeInTheDocument();
  });

  it('should not display distance for players who did not guess', () => {
    store.setState((s) => {
      s.game.scoringMode = 'Distance';
      s.game.lastRoundResult = {
        results: [
          {
            nickname: 'Player1',
            guess: null,
            correct_code: 'BOS',
            score_awarded: 0,
            current_total_score: 100,
            distance_km: undefined,
          },
        ],
        next_host_nickname: null,
      };
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText(/No guess/)).toBeInTheDocument();
    expect(screen.queryByText(/km away/)).not.toBeInTheDocument();
  });

  it('should not display distance in Exact mode even if distance_km is provided', () => {
    store.setState((s) => {
      s.game.scoringMode = 'Exact';
      s.game.lastRoundResult = {
        results: [
          {
            nickname: 'Player1',
            guess: 'JFK',
            correct_code: 'BOS',
            score_awarded: 0,
            current_total_score: 100,
            distance_km: 305.5, // Backend shouldn't send this, but testing UI behavior
          },
        ],
        next_host_nickname: null,
      };
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.queryByText(/km away/)).not.toBeInTheDocument();
  });

  it('should format large distances with comma separator', () => {
    store.setState((s) => {
      s.game.scoringMode = 'Distance';
      s.game.lastRoundResult = {
        results: [
          {
            nickname: 'Player1',
            guess: 'LAX',
            correct_code: 'BOS',
            score_awarded: 0,
            current_total_score: 100,
            distance_km: 4178.5,
          },
        ],
        next_host_nickname: null,
      };
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText(/4,179 km away/)).toBeInTheDocument();
  });

  describe('when the server sends no distance for a guess', () => {
    // An airport without coordinates makes the server send distance_km: null
    const setDistanceResultWithoutDistance = () => {
      store.setState((s) => {
        s.game.scoringMode = 'Distance';
        s.game.lastRoundResult = {
          results: [
            {
              nickname: 'Player1',
              guess: 'ORD',
              correct_code: 'KJFK',
              score_awarded: 0,
              current_total_score: 0,
              distance_km: null,
            },
          ],
          next_host_nickname: null,
        };
      });
    };

    it('renders the guess without a distance in standard mode', () => {
      setDistanceResultWithoutDistance();

      renderWithStore(<RoundResultModal />);

      expect(screen.getByText('Guessed: ORD')).toBeInTheDocument();
      expect(screen.queryByText(/km away/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Exact match!/)).not.toBeInTheDocument();
    });

    it('renders the guess without a distance in retro mode', () => {
      store.getState().ui.toggleRetroMode();
      setDistanceResultWithoutDistance();

      renderWithStore(<RoundResultModal />);

      expect(screen.getByText('Round Complete')).toBeInTheDocument();
      expect(screen.getByText('ORD')).toBeInTheDocument();
      expect(screen.queryByText(/km\)/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Exact/)).not.toBeInTheDocument();
    });
  });

  it('should display distances in retro mode', () => {
    store.getState().ui.toggleRetroMode();
    store.setState((s) => {
      s.game.scoringMode = 'Distance';
      s.game.lastRoundResult = {
        results: [
          {
            nickname: 'Player1',
            guess: 'BOS',
            correct_code: 'BOS',
            score_awarded: 100,
            current_total_score: 200,
            distance_km: 0,
          },
          {
            nickname: 'Player2',
            guess: 'LAX',
            correct_code: 'BOS',
            score_awarded: 0,
            current_total_score: 100,
            distance_km: 4178.5,
          },
        ],
        next_host_nickname: null,
      };
    });

    renderWithStore(<RoundResultModal />);

    expect(screen.getByText('(Exact)')).toBeInTheDocument();
    expect(screen.getByText('(4,179km)')).toBeInTheDocument();
  });
});
