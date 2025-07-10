import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CurrentHostDisplay } from './CurrentHostDisplay';

// Mock the store hook
vi.mock('../../hooks/useStore', () => ({
  useStore: vi.fn(),
}));

// Import after mock
import { useStore } from '../../hooks/useStore';

describe('CurrentHostDisplay', () => {
  it('renders host information when hostNickname exists', () => {
    vi.mocked(useStore).mockReturnValue('PlayerHost');

    render(<CurrentHostDisplay />);

    expect(screen.getByText('Host:')).toBeInTheDocument();
    expect(screen.getByText('PlayerHost')).toBeInTheDocument();
  });

  it('returns null when no hostNickname', () => {
    vi.mocked(useStore).mockReturnValue(null);

    const { container } = render(<CurrentHostDisplay />);

    expect(container.firstChild).toBeNull();
  });

  it('applies custom className', () => {
    vi.mocked(useStore).mockReturnValue('TestHost');

    render(<CurrentHostDisplay className="mt-4" />);

    const container = screen.getByText('Host:').parentElement;
    expect(container).toHaveClass('mt-4');
  });

  it('updates when host changes', () => {
    const { rerender } = render(<CurrentHostDisplay />);

    // Initial host
    vi.mocked(useStore).mockReturnValue('HostA');
    rerender(<CurrentHostDisplay />);
    expect(screen.getByText('HostA')).toBeInTheDocument();

    // Host changes
    vi.mocked(useStore).mockReturnValue('HostB');
    rerender(<CurrentHostDisplay />);
    expect(screen.getByText('HostB')).toBeInTheDocument();
  });
});
