import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import GuessForm from './GuessForm';
import { useGuess } from '../hooks/useGuess';
import type { Airport } from '../../../components/AirportAutocomplete';

// Mock the useGuess hook
vi.mock('../hooks/useGuess');

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
    expect(screen.getByText(/Where is this flight/)).toBeInTheDocument();
    expect(screen.getByText('(30s)')).toBeInTheDocument();
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

    expect(screen.queryByText(/\(\d+s\)/)).not.toBeInTheDocument();
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
});
