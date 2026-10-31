import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { ScoreModeIndicator } from './ScoreModeIndicator';
import { createRootStore } from '../../store/createRootStore';
import { StoreContext } from '../../store/createRootStore';

describe('ScoreModeIndicator', () => {
  let store: ReturnType<typeof createRootStore>;

  beforeEach(() => {
    store = createRootStore();
    // Toggle retroMode off (default is true) to test standard mode UI
    store.getState().ui.toggleRetroMode();
  });

  const renderWithStore = (component: React.ReactElement) => {
    return render(
      <StoreContext.Provider value={store}>
        {component}
      </StoreContext.Provider>
    );
  };

  it('should not render when no scoring mode', () => {
    const { container } = renderWithStore(<ScoreModeIndicator />);
    expect(container.firstChild).toBeNull();
  });

  it('should render Exact mode indicator', () => {
    store.setState((s) => { s.game.scoringMode = 'Exact'; });
    renderWithStore(<ScoreModeIndicator />);

    expect(screen.getByText('Mode:')).toBeInTheDocument();
    expect(screen.getByText(/Exact/)).toBeInTheDocument();
  });

  it('should render Distance mode indicator', () => {
    store.setState((s) => { s.game.scoringMode = 'Distance'; });
    renderWithStore(<ScoreModeIndicator />);

    expect(screen.getByText('Mode:')).toBeInTheDocument();
    expect(screen.getByText(/Distance/)).toBeInTheDocument();
  });

  it('should show user score when nickname exists', () => {
    store.setState((s) => { s.game.scoringMode = 'Exact'; });
    store.getState().connection.setConnectionDetails({ roomCode: 'ABCD', wsUrl: 'ws://x', nickname: 'TestPlayer' });
    store.getState().game.applyDelta({ scores: { TestPlayer: 150 } });

    renderWithStore(<ScoreModeIndicator />);

    expect(screen.getByText('Score:')).toBeInTheDocument();
    expect(screen.getByText('150')).toBeInTheDocument();
  });

  it('should show zero score for new player', () => {
    store.setState((s) => { s.game.scoringMode = 'Exact'; });
    store.getState().connection.setConnectionDetails({ roomCode: 'ABCD', wsUrl: 'ws://x', nickname: 'NewPlayer' });

    renderWithStore(<ScoreModeIndicator />);

    expect(screen.getByText('Score:')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('should show timer when round is active', () => {
    store.setState((s) => {
      s.game.scoringMode = 'Exact';
      s.game.round = { state: 'guessing', round_number: 1 };
      s.game.roundTimeout = 30;
    });

    renderWithStore(<ScoreModeIndicator />);

    expect(screen.getByText('Time:')).toBeInTheDocument();
    expect(screen.getByText('30s')).toBeInTheDocument();
  });

  it('should countdown timer', async () => {
    vi.useFakeTimers();

    store.setState((s) => {
      s.game.scoringMode = 'Exact';
      s.game.round = { state: 'guessing', round_number: 1 };
      s.game.roundTimeout = 30;
    });

    renderWithStore(<ScoreModeIndicator />);

    expect(screen.getByText('30s')).toBeInTheDocument();

    // Advance timer by 1 second
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(screen.getByText('29s')).toBeInTheDocument();

    // Advance to near end
    act(() => {
      vi.advanceTimersByTime(20000);
    });

    expect(screen.getByText('9s')).toBeInTheDocument();

    vi.useRealTimers();
  });

  it('should show urgent styling when time is low', async () => {
    vi.useFakeTimers();

    store.setState((s) => {
      s.game.scoringMode = 'Exact';
      s.game.round = { state: 'guessing', round_number: 1 };
      s.game.roundTimeout = 15;
    });

    renderWithStore(<ScoreModeIndicator />);

    // Advance to urgent time (10s or less)
    act(() => {
      vi.advanceTimersByTime(6000);
    });

    const timerElement = screen.getByText('9s');
    expect(timerElement).toHaveClass('text-red-600');
    // Check for animate-pulse class on the timer container
    const timerContainer = screen.getByText('Time:').parentElement;
    expect(timerContainer).toHaveClass('animate-pulse');

    vi.useRealTimers();
  });

  it('should not show timer when round is not active', () => {
    store.setState((s) => {
      s.game.scoringMode = 'Exact';
      s.game.round = { state: 'waiting_for_selection', round_number: 1 };
      s.game.roundTimeout = 30;
    });

    renderWithStore(<ScoreModeIndicator />);

    expect(screen.queryByText('Time:')).not.toBeInTheDocument();
  });

  it('should accept custom className', () => {
    store.setState((s) => { s.game.scoringMode = 'Exact'; });

    const { container } = renderWithStore(<ScoreModeIndicator className="custom-class" />);

    expect(container.firstChild).toHaveClass('custom-class');
  });
});
