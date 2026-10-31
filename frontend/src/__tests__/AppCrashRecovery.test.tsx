import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

vi.mock('../pages/HomePage', () => ({
  default: function CrashingHomePage(): JSX.Element {
    throw new Error('home page crashed');
  },
}));

describe('App', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the crash recovery screen instead of a blank page when a view throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    localStorage.clear();

    render(<App />);

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });
});
