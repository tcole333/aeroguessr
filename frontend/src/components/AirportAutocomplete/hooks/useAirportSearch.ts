import { useState, useEffect, useCallback, useMemo } from 'react';
import Fuse from 'fuse.js';
import type { Airport, AirportSearchResult, UseAirportSearchResult } from '../types';
import airportsData from '../../../assets/airports.json';

const fuseOptions: Fuse.IFuseOptions<Airport> = {
  keys: [
    { name: 'name', weight: 0.3 },
    { name: 'municipality', weight: 0.3 },
    { name: 'iata', weight: 0.2 },
    { name: 'icao', weight: 0.2 }
  ],
  threshold: 0.3,
  includeScore: true,
  minMatchCharLength: 2,
  shouldSort: true,
  findAllMatches: false,
  location: 0,
  distance: 100,
  useExtendedSearch: false,
  ignoreLocation: false,
  ignoreFieldNorm: false,
  fieldNormWeight: 1
};

export function useAirportSearch(): UseAirportSearchResult {
  const [results, setResults] = useState<AirportSearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [fuse, setFuse] = useState<Fuse<Airport> | null>(null);

  // Initialize Fuse.js with airport data
  useEffect(() => {
    // Use setTimeout to ensure loading state is visible on first render
    const timer = setTimeout(() => {
      try {
        // Type assertion since we know the structure matches
        const airports = airportsData as Airport[];
        const fuseInstance = new Fuse(airports, fuseOptions);
        setFuse(fuseInstance);
        setIsLoading(false);
      } catch (error) {
        console.error('Failed to initialize airport search:', error);
        setIsLoading(false);
      }
    }, 0);

    return () => clearTimeout(timer);
  }, []);

  const search = useCallback((query: string) => {
    if (!fuse || !query || query.length < 2) {
      setResults([]);
      return;
    }

    const searchResults = fuse.search(query, { limit: 10 });

    // Transform Fuse results to our format
    const transformedResults: AirportSearchResult[] = searchResults.map(result => ({
      ...result.item,
      score: result.score
    }));

    setResults(transformedResults);
  }, [fuse]);

  const clearResults = useCallback(() => {
    setResults([]);
  }, []);

  return {
    results,
    isLoading,
    search,
    clearResults
  };
}
