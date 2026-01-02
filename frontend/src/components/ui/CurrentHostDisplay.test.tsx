import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CurrentHostDisplay } from './CurrentHostDisplay';

// Mock the store hook
vi.mock('../../hooks/useStore', () => ({
  useStore: vi.fn(),
}));

// Import after mock
import { useStore } from '../../hooks/useStore';

// Create mock implementation that handles multiple selectors
const createMockUseStore = (hostNickname: string | null) => {
  return vi.fn((selector) => {
    // Create a mock state
    const state = {
      game: { hostNickname },
      ui: { retroMode: false },
    };
    return selector(state);
  });
};

describe('CurrentHostDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders host information when hostNickname exists', () => {
    vi.mocked(useStore).mockImplementation(createMockUseStore('PlayerHost'));

    render(<CurrentHostDisplay />);

    expect(screen.getByText('Host:')).toBeInTheDocument();
    expect(screen.getByText('PlayerHost')).toBeInTheDocument();
  });

  it('returns null when no hostNickname', () => {
    vi.mocked(useStore).mockImplementation(createMockUseStore(null));

    const { container } = render(<CurrentHostDisplay />);

    expect(container.firstChild).toBeNull();
  });

  it('applies custom className', () => {
    vi.mocked(useStore).mockImplementation(createMockUseStore('TestHost'));

    render(<CurrentHostDisplay className="mt-4" />);

    const container = screen.getByText('Host:').parentElement;
    expect(container).toHaveClass('mt-4');
  });

  it('updates when host changes', () => {
    vi.mocked(useStore).mockImplementation(createMockUseStore('HostA'));
    const { rerender } = render(<CurrentHostDisplay />);
    expect(screen.getByText('HostA')).toBeInTheDocument();

    // Host changes
    vi.mocked(useStore).mockImplementation(createMockUseStore('HostB'));
    rerender(<CurrentHostDisplay />);
    expect(screen.getByText('HostB')).toBeInTheDocument();
  });
});
