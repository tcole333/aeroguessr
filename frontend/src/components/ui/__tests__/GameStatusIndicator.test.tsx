import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { GameStatusIndicator } from '../GameStatusIndicator';
import { useStore } from '../../../hooks/useStore';

// Mock the store hook
vi.mock('../../../hooks/useStore', () => ({
  useStore: vi.fn(),
}));

// Helper to create mock state with retroMode set to false by default
const createMockState = (overrides: {
  game?: Partial<{
    round: { state: string; round_number: number } | null;
    roundTimeout: number | null;
    hostNickname: string;
    isSolo: boolean;
  }>;
  connection?: Partial<{ nickname: string }>;
  ui?: Partial<{ retroMode: boolean }>;
} = {}) => ({
  game: {
    round: null,
    roundTimeout: null,
    hostNickname: 'host',
    isSolo: false,
    ...overrides.game,
  },
  connection: {
    nickname: 'player',
    ...overrides.connection,
  },
  ui: {
    retroMode: false,
    ...overrides.ui,
  },
});

describe('GameStatusIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Phase descriptions', () => {
    it('shows solo mode message when in solo mode', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { isSolo: true },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Solo Mode - Click any plane to guess')).toBeInTheDocument();
    });

    it('shows host waiting message when host and no round', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          connection: { nickname: 'host' },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Select a plane to start round')).toBeInTheDocument();
    });

    it('shows player waiting message when not host and no round', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState();
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Waiting for game to start')).toBeInTheDocument();
    });

    it('shows waiting for selection message', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'waiting_for_selection', round_number: 1 } },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Waiting for plane selection')).toBeInTheDocument();
    });

    it('shows select plane message for host during waiting phase', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'waiting_for_selection', round_number: 1 } },
          connection: { nickname: 'host' },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Select a plane')).toBeInTheDocument();
    });

    it('shows submit guess message during guessing phase', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'guessing', round_number: 2 }, roundTimeout: 30 },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Submit your guess')).toBeInTheDocument();
    });

    it('shows round complete message during results phase', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'showing_results', round_number: 3 } },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Round complete')).toBeInTheDocument();
    });
  });

  describe('Round number display', () => {
    it('shows round number when available', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'guessing', round_number: 5 }, roundTimeout: 30 },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Round:')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('does not show round number when round number is 0', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'waiting_for_selection', round_number: 0 } },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.queryByText('Round:')).not.toBeInTheDocument();
    });
  });

  describe('Timer functionality', () => {
    it('shows timer during guessing phase', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'guessing', round_number: 2 }, roundTimeout: 30 },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Time:')).toBeInTheDocument();
      expect(screen.getByText('0:30')).toBeInTheDocument();
    });

    it('shows timer during accepting_guesses phase', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'accepting_guesses', round_number: 2 }, roundTimeout: 45 },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('Time:')).toBeInTheDocument();
      expect(screen.getByText('0:45')).toBeInTheDocument();
    });

    it('counts down timer correctly', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'guessing', round_number: 2 }, roundTimeout: 30 },
        });
        return selector(state);
      });

      const { rerender } = render(<GameStatusIndicator />);
      expect(screen.getByText('0:30')).toBeInTheDocument();

      // Advance timer by 5 seconds
      act(() => {
        vi.advanceTimersByTime(5000);
      });
      rerender(<GameStatusIndicator />);
      expect(screen.getByText('0:25')).toBeInTheDocument();

      // Advance timer by 20 more seconds
      act(() => {
        vi.advanceTimersByTime(20000);
      });
      rerender(<GameStatusIndicator />);
      expect(screen.getByText('0:05')).toBeInTheDocument();
    });

    it('formats time correctly for minutes', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'guessing', round_number: 2 }, roundTimeout: 125 },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.getByText('2:05')).toBeInTheDocument();
    });

    it('does not show timer when not guessing', () => {
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'showing_results', round_number: 2 }, roundTimeout: 30 },
        });
        return selector(state);
      });

      render(<GameStatusIndicator />);
      expect(screen.queryByText('Time:')).not.toBeInTheDocument();
    });
  });

  describe('Visual states', () => {
    it('applies correct colors for different phases', () => {
      // Test waiting phase
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'waiting_for_selection', round_number: 1 } },
        });
        return selector(state);
      });

      const { rerender } = render(<GameStatusIndicator />);
      let phaseText = screen.getByText('Waiting for plane selection');
      expect(phaseText).toHaveClass('text-blue-600');

      // Test guessing phase
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'guessing', round_number: 1 }, roundTimeout: 30 },
        });
        return selector(state);
      });

      rerender(<GameStatusIndicator />);
      phaseText = screen.getByText('Submit your guess');
      expect(phaseText).toHaveClass('text-green-600');

      // Test results phase
      vi.mocked(useStore).mockImplementation((selector) => {
        const state = createMockState({
          game: { round: { state: 'showing_results', round_number: 1 } },
        });
        return selector(state);
      });

      rerender(<GameStatusIndicator />);
      phaseText = screen.getByText('Round complete');
      expect(phaseText).toHaveClass('text-purple-600');
    });
  });
});
