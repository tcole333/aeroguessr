import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import GuessForm from './GuessForm';
import { useGuess } from '../hooks/useGuess';
import type { Airport } from '../../../components/AirportAutocomplete';

// Mock the useGuess hook
vi.mock('../hooks/useGuess');

// Default mock state
let mockRound: { direction?: string; state?: string; hex?: string } | null = null;
let mockUsedPlanes = new Set<string>();

// Mock the useStore hook with a mock state
vi.mock('../../../hooks/useStore', () => ({
  useStore: vi.fn((selector) => {
    // Create a mock state that the selectors can use
    const mockState = {
      ui: { retroMode: false },
      game: { round: mockRound, usedPlaneHexes: mockUsedPlanes },
      planes: { values: {} },  // Use 'values' not 'byId' to match selector
    };
    // If selector is a function, call it with the mock state
    if (typeof selector === 'function') {
      return selector(mockState);
    }
    return undefined;
  }),
}));

// Mock the AirportAutocomplete component
vi.mock('../../../components/AirportAutocomplete', () => ({
  AirportAutocomplete: ({
    value,
    onChange,
    onSelect,
    disabled,
    placeholder,
    'aria-label': ariaLabel,
    'aria-describedby': ariaDescribedBy,
    autoFocus,
    id,
    className
  }: React.ComponentProps<typeof import('../../../components/AirportAutocomplete').AirportAutocomplete>) => (
    <div>
      <input
        id={id}
        data-testid="airport-autocomplete"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder={placeholder}
        aria-label={ariaLabel}
        aria-describedby={ariaDescribedBy}
        autoFocus={autoFocus}
        className={className}
      />
      <button
        type="button"
        data-testid="select-sfo"
        onClick={() => onSelect({
          iata: 'SFO',
          icao: 'KSFO',
          name: 'San Francisco International Airport',
          municipality: 'San Francisco',
          country: 'United States',
          lat: 37.6213,
          lon: -122.3790
        } as Airport)}
      >
        Select SFO
      </button>
    </div>
  )
}));

const mockUseGuess = useGuess as ReturnType<typeof vi.fn>;

describe('GuessForm', () => {
  const defaultMockValues = {
    inputValue: '',
    selectedAirport: null,
    disabled: false,
    error: null,
    remaining: 30,
    visible: true,
    setInputValue: vi.fn(),
    setSelectedAirport: vi.fn(),
    handleSubmit: vi.fn((e) => e.preventDefault()),
    dismiss: vi.fn(),
    code: '',
    setCode: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseGuess.mockReturnValue(defaultMockValues);
    // Reset mock state
    mockRound = null;
    mockUsedPlanes = new Set<string>();
  });

  it('should not render when not visible', () => {
    mockUseGuess.mockReturnValue({
      ...defaultMockValues,
      visible: false,
    });

    const { container } = render(<GuessForm />);
    expect(container.firstChild).toBeNull();
  });

  it('should render the airport autocomplete when visible', () => {
    render(<GuessForm />);

    expect(screen.getByTestId('airport-autocomplete')).toBeInTheDocument();
    expect(screen.getByText(/Guess the destination/)).toBeInTheDocument();
    expect(screen.getByText('(30)')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Type city or airport code...')).toBeInTheDocument();
  });

  it('should update input value when typing', async () => {
    const user = userEvent.setup();
    render(<GuessForm />);

    const input = screen.getByTestId('airport-autocomplete');
    await user.type(input, 'San');

    // User event types one character at a time, so we expect individual calls
    expect(defaultMockValues.setInputValue).toHaveBeenCalledWith('S');
    expect(defaultMockValues.setInputValue).toHaveBeenCalledWith('a');
    expect(defaultMockValues.setInputValue).toHaveBeenCalledWith('n');
    expect(defaultMockValues.setInputValue).toHaveBeenCalledTimes(3);
  });

  it('should handle airport selection', async () => {
    const user = userEvent.setup();
    render(<GuessForm />);

    const selectButton = screen.getByTestId('select-sfo');
    await user.click(selectButton);

    expect(defaultMockValues.setSelectedAirport).toHaveBeenCalledWith({
      iata: 'SFO',
      icao: 'KSFO',
      name: 'San Francisco International Airport',
      municipality: 'San Francisco',
      country: 'United States',
      lat: 37.6213,
      lon: -122.3790
    });
    // setInputValue is no longer called directly in handleAirportSelect
    // to prevent circular updates with the AirportAutocomplete
  });

  it('should display selected airport info', () => {
    mockUseGuess.mockReturnValue({
      ...defaultMockValues,
      selectedAirport: {
        iata: 'JFK',
        icao: 'KJFK',
        name: 'John F Kennedy International Airport',
        municipality: 'New York',
        country: 'United States',
        lat: 40.6413,
        lon: -73.7781
      },
    });

    render(<GuessForm />);

    expect(screen.getByText('Selected: John F Kennedy International Airport (JFK)')).toBeInTheDocument();
  });

  it('should display error message when present', () => {
    mockUseGuess.mockReturnValue({
      ...defaultMockValues,
      error: 'Invalid airport code format',
    });

    render(<GuessForm />);

    const errorElement = screen.getByRole('alert');
    expect(errorElement).toHaveTextContent('Invalid airport code format');
    expect(screen.getByTestId('airport-autocomplete')).toHaveAttribute('aria-describedby', 'guess-error');
  });

  it('should disable input and show different button text when guess is submitted', () => {
    mockUseGuess.mockReturnValue({
      ...defaultMockValues,
      disabled: true,
    });

    render(<GuessForm />);

    expect(screen.getByTestId('airport-autocomplete')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Guess Submitted' })).toBeDisabled();
  });

  it('should submit form when button is clicked', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn((e) => e.preventDefault());

    mockUseGuess.mockReturnValue({
      ...defaultMockValues,
      handleSubmit,
    });

    render(<GuessForm />);

    const submitButton = screen.getByRole('button', { name: 'Submit Guess' });
    await user.click(submitButton);

    expect(handleSubmit).toHaveBeenCalled();
  });

  it('should dismiss modal when clicking backdrop', async () => {
    const user = userEvent.setup();
    render(<GuessForm />);

    const backdrop = screen.getByRole('dialog');
    await user.click(backdrop);

    expect(defaultMockValues.dismiss).toHaveBeenCalled();
  });

  it('should not dismiss modal when clicking form content', async () => {
    const user = userEvent.setup();
    render(<GuessForm />);

    // Click on the form by using a known element within it
    const submitButton = screen.getByRole('button', { name: 'Submit Guess' });
    const form = submitButton.parentElement as HTMLElement;
    await user.click(form);

    expect(defaultMockValues.dismiss).not.toHaveBeenCalled();
  });

  it('should not show remaining time when null', () => {
    mockUseGuess.mockReturnValue({
      ...defaultMockValues,
      remaining: null,
    });

    render(<GuessForm />);

    // Timer format changed from (30s) to (30) - no 's' suffix
    expect(screen.queryByText(/\(\d+\)/)).not.toBeInTheDocument();
  });

  it('should have proper accessibility attributes', () => {
    render(<GuessForm />);

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    const input = screen.getByTestId('airport-autocomplete');
    expect(input).toHaveAttribute('aria-label', 'Airport guess');
    expect(input).toHaveAttribute('id', 'airport-guess');
    // autoFocus is a prop, not an HTML attribute - it affects behavior but isn't reflected in DOM
  });

  it('should handle airport with only ICAO code', () => {
    mockUseGuess.mockReturnValue({
      ...defaultMockValues,
      selectedAirport: {
        iata: '',
        icao: 'LFPG',
        name: 'Charles de Gaulle Airport',
        municipality: 'Paris',
        country: 'France',
        lat: 49.0097,
        lon: 2.5477
      },
    });

    render(<GuessForm />);

    expect(screen.getByText('Selected: Charles de Gaulle Airport (LFPG)')).toBeInTheDocument();
  });

  describe('direction-based display', () => {
    it('should show "Guess the origin" when direction is origin', () => {
      mockRound = { direction: 'origin', state: 'guessing', hex: 'abc123' };

      render(<GuessForm />);

      expect(screen.getByText(/Guess the origin/)).toBeInTheDocument();
    });

    it('should show "Guess the destination" when direction is destination', () => {
      mockRound = { direction: 'destination', state: 'guessing', hex: 'abc123' };

      render(<GuessForm />);

      expect(screen.getByText(/Guess the destination/)).toBeInTheDocument();
    });

    it('should default to destination when direction is not set', () => {
      mockRound = { state: 'guessing', hex: 'abc123' };

      render(<GuessForm />);

      expect(screen.getByText(/Guess the destination/)).toBeInTheDocument();
    });
  });
});
