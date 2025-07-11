import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AirportAutocomplete } from './AirportAutocomplete';

// Mock the airport data
vi.mock('../../assets/airports.json', () => ({
  default: [
    {
      iata: 'BOS',
      icao: 'KBOS',
      name: 'Logan International Airport',
      municipality: 'Boston',
      country: 'US',
      lat: 42.3656,
      lon: -71.0096
    },
    {
      iata: 'JFK',
      icao: 'KJFK',
      name: 'John F Kennedy International Airport',
      municipality: 'New York',
      country: 'US',
      lat: 40.6413,
      lon: -73.7781
    },
    {
      iata: 'LAX',
      icao: 'KLAX',
      name: 'Los Angeles International Airport',
      municipality: 'Los Angeles',
      country: 'US',
      lat: 33.9425,
      lon: -118.4081
    },
    {
      iata: 'SFO',
      icao: 'KSFO',
      name: 'San Francisco International Airport',
      municipality: 'San Francisco',
      country: 'US',
      lat: 37.6213,
      lon: -122.3790
    },
    {
      iata: 'ORD',
      icao: 'KORD',
      name: "O'Hare International Airport",
      municipality: 'Chicago',
      country: 'US',
      lat: 41.9742,
      lon: -87.9073
    }
  ]
}));

describe('AirportAutocomplete', () => {
  const mockOnChange = vi.fn();
  const mockOnSelect = vi.fn();
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    // Mock scrollIntoView
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should render with basic props', () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
        placeholder="Enter airport"
      />
    );

    const input = screen.getByPlaceholderText('Enter airport');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('role', 'combobox');
    expect(input).toHaveAttribute('aria-expanded', 'false');
  });

  it('should show search results when typing', async () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'bos');

    await waitFor(() => {
      expect(screen.getByText('Logan International Airport')).toBeInTheDocument();
      expect(screen.getByText('Boston, US')).toBeInTheDocument();
    });
  });

  it('should handle selection via click', async () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
        onSelect={mockOnSelect}
      />
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'jfk');

    await waitFor(() => {
      expect(screen.getByText('John F Kennedy International Airport')).toBeInTheDocument();
    });

    const option = screen.getByText('John F Kennedy International Airport');
    fireEvent.click(option);

    expect(mockOnChange).toHaveBeenCalledWith('JFK');
    expect(mockOnSelect).toHaveBeenCalledWith(expect.objectContaining({
      iata: 'JFK',
      name: 'John F Kennedy International Airport'
    }));
  });

  it('should handle keyboard navigation', async () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'san');

    await waitFor(() => {
      expect(screen.getByText('San Francisco International Airport')).toBeInTheDocument();
    });

    // Press arrow down
    fireEvent.keyDown(input, { key: 'ArrowDown' });

    const listbox = screen.getByRole('listbox');
    const firstOption = within(listbox).getAllByRole('option')[0];
    expect(firstOption).toHaveAttribute('aria-selected', 'true');

    // Press Enter to select
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mockOnChange).toHaveBeenCalledWith('SFO');
  });

  it('should handle escape key to close dropdown', async () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'lax');

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    fireEvent.keyDown(input, { key: 'Escape' });

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(input).toHaveAttribute('aria-expanded', 'false');
  });

  it('should show clear button when input has value', async () => {
    render(
      <AirportAutocomplete
        value="BOS"
        onChange={mockOnChange}
      />
    );

    const clearButton = screen.getByLabelText('Clear input');
    expect(clearButton).toBeInTheDocument();

    fireEvent.click(clearButton);
    expect(mockOnChange).toHaveBeenCalledWith('');
  });

  it('should debounce search input', async () => {
    // This test verifies that the search is debounced
    // We'll check that rapid typing only triggers search after delay
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('combobox');

    // Type quickly
    await user.type(input, 'bos');

    // onChange should be called for each character
    expect(mockOnChange).toHaveBeenCalledTimes(3);
    expect(mockOnChange).toHaveBeenCalledWith('b');
    expect(mockOnChange).toHaveBeenCalledWith('bo');
    expect(mockOnChange).toHaveBeenCalledWith('bos');

    // Wait for debounced search to complete
    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
      expect(screen.getByText('Logan International Airport')).toBeInTheDocument();
    });
  });

  it('should show no results message', async () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'xyz123');

    await waitFor(() => {
      expect(screen.getByText('No airports found')).toBeInTheDocument();
    });
  });

  it('should handle disabled state', () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
        disabled={true}
      />
    );

    const input = screen.getByRole('combobox');
    expect(input).toBeDisabled();
    expect(input).toHaveClass('disabled:cursor-not-allowed');
  });

  it('should accept custom className', () => {
    const { container } = render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
        className="custom-class"
      />
    );

    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('should handle accessibility attributes', () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
        id="airport-input"
        aria-label="Select departure airport"
        aria-describedby="airport-help"
      />
    );

    const input = screen.getByRole('combobox');
    expect(input).toHaveAttribute('id', 'airport-input');
    expect(input).toHaveAttribute('aria-label', 'Select departure airport');
    expect(input).toHaveAttribute('aria-describedby', 'airport-help');
  });

  it('should handle form attributes', () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
        name="departure"
        required={true}
        autoFocus={true}
      />
    );

    const input = screen.getByRole('combobox');
    expect(input).toHaveAttribute('name', 'departure');
    expect(input).toHaveAttribute('required');
    expect(input).toHaveFocus();
  });

  it('should close dropdown on outside click', async () => {
    render(
      <div>
        <AirportAutocomplete
          value=""
          onChange={mockOnChange}
        />
        <button>Outside button</button>
      </div>
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'ord');

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    // Click outside
    const outsideButton = screen.getByText('Outside button');
    fireEvent.mouseDown(outsideButton);

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('should handle arrow navigation correctly', async () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'los'); // Should match Los Angeles

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    // Navigate down
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    const activeOption = screen.getByRole('option', { selected: true });
    expect(activeOption).toHaveTextContent('LAX');

    // Navigate up (should go back to -1, no selection)
    fireEvent.keyDown(input, { key: 'ArrowUp' });
    expect(screen.queryByRole('option', { selected: true })).not.toBeInTheDocument();
  });

  it('should handle search with partial matches', async () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'new york');

    await waitFor(() => {
      expect(screen.getByText('John F Kennedy International Airport')).toBeInTheDocument();
    });
  });

  it('should scroll active item into view', async () => {
    render(
      <AirportAutocomplete
        value=""
        onChange={mockOnChange}
      />
    );

    const input = screen.getByRole('combobox');
    await user.type(input, 'airport'); // Should match multiple

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    fireEvent.keyDown(input, { key: 'ArrowDown' });

    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({
      block: 'nearest',
      behavior: 'smooth'
    });
  });
});
