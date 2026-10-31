import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAirportSearch } from './useAirportSearch';

// Mock the airport data
vi.mock('@data/airports.json', () => ({
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
      iata: 'CDG',
      icao: 'LFPG',
      name: 'Charles de Gaulle Airport',
      municipality: 'Paris',
      country: 'FR',
      lat: 49.0097,
      lon: 2.5479
    },
    {
      iata: 'LHR',
      icao: 'EGLL',
      name: 'London Heathrow Airport',
      municipality: 'London',
      country: 'GB',
      lat: 51.4700,
      lon: -0.4543
    }
  ]
}));

describe('useAirportSearch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should initialize with loading state', () => {
    const { result } = renderHook(() => useAirportSearch());

    expect(result.current.isLoading).toBe(true);
    expect(result.current.results).toEqual([]);
  });

  it('should set loading to false after initialization', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });

  it('should search by IATA code', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('BOS');
    });

    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0]).toMatchObject({
      iata: 'BOS',
      name: 'Logan International Airport',
      municipality: 'Boston'
    });
  });

  it('should search by airport name', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('Logan');
    });

    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0].iata).toBe('BOS');
  });

  it('should search by municipality', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('New York');
    });

    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0].iata).toBe('JFK');
  });

  it('should handle fuzzy search with typos', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('los agneles'); // Typo in Angeles
    });

    expect(result.current.results.length).toBeGreaterThan(0);
    expect(result.current.results[0].iata).toBe('LAX');
  });

  it('should limit results to 10', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('airport'); // Should match all airports
    });

    expect(result.current.results.length).toBeLessThanOrEqual(10);
  });

  it('should clear results', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('BOS');
    });

    expect(result.current.results).toHaveLength(1);

    act(() => {
      result.current.clearResults();
    });

    expect(result.current.results).toEqual([]);
  });

  it('should not search with query less than 2 characters', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('B');
    });

    expect(result.current.results).toEqual([]);
  });

  it('should handle empty query', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('');
    });

    expect(result.current.results).toEqual([]);
  });

  it('should include score in results', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('JFK');
    });

    expect(result.current.results[0]).toHaveProperty('score');
    expect(typeof result.current.results[0].score).toBe('number');
  });


  it('should perform case-insensitive search', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    act(() => {
      result.current.search('cdg');
    });

    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0].iata).toBe('CDG');

    act(() => {
      result.current.search('CDG');
    });

    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0].iata).toBe('CDG');
  });

  it('should measure search performance', async () => {
    const { result } = renderHook(() => useAirportSearch());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const startTime = performance.now();

    act(() => {
      result.current.search('London');
    });

    const endTime = performance.now();
    const searchTime = endTime - startTime;

    // Search should complete in less than 50ms
    expect(searchTime).toBeLessThan(50);
    expect(result.current.results[0].iata).toBe('LHR');
  });
});
