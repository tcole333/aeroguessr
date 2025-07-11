export interface Airport {
  iata: string;
  icao: string;
  name: string;
  municipality: string;
  country: string;
  lat: number;
  lon: number;
}

export interface AirportAutocompleteProps {
  value: string;
  onChange: (code: string) => void;
  onSelect?: (airport: Airport) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
  name?: string;
  required?: boolean;
  autoFocus?: boolean;
  'aria-label'?: string;
  'aria-describedby'?: string;
}

export interface AirportSearchResult extends Airport {
  score?: number;
}

export interface UseAirportSearchResult {
  results: AirportSearchResult[];
  isLoading: boolean;
  search: (query: string) => void;
  clearResults: () => void;
}
