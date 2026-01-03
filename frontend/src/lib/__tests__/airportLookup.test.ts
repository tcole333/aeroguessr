import { describe, it, expect } from 'vitest';
import { getAirportByCode, formatAirportDisplay } from '../airportLookup';

describe('getAirportByCode', () => {
  it('returns airport by ICAO code', () => {
    const airport = getAirportByCode('KBOS');
    expect(airport).not.toBeNull();
    expect(airport?.icao).toBe('KBOS');
    expect(airport?.iata).toBe('BOS');
    expect(airport?.municipality).toBe('Boston');
  });

  it('returns airport by IATA code', () => {
    const airport = getAirportByCode('LAX');
    expect(airport).not.toBeNull();
    expect(airport?.icao).toBe('KLAX');
    expect(airport?.municipality).toBe('Los Angeles');
  });

  it('is case-insensitive', () => {
    const upper = getAirportByCode('KBOS');
    const lower = getAirportByCode('kbos');
    const mixed = getAirportByCode('Kbos');

    expect(upper?.icao).toBe(lower?.icao);
    expect(upper?.icao).toBe(mixed?.icao);
  });

  it('returns null for unknown code', () => {
    expect(getAirportByCode('ZZZZ')).toBeNull();
    expect(getAirportByCode('XXXX')).toBeNull();
  });

  it('returns null for empty/null input', () => {
    expect(getAirportByCode('')).toBeNull();
  });
});

describe('formatAirportDisplay', () => {
  describe('single-airport cities (use city name)', () => {
    it('shows city name for Boston', () => {
      expect(formatAirportDisplay('KBOS')).toBe('Boston');
      expect(formatAirportDisplay('BOS')).toBe('Boston');
    });

    it('shows city name for Denver', () => {
      expect(formatAirportDisplay('KDEN')).toBe('Denver');
    });

    it('shows city name for Seattle', () => {
      expect(formatAirportDisplay('KSEA')).toBe('Seattle');
    });

    it('shows city name for Phoenix', () => {
      expect(formatAirportDisplay('KPHX')).toBe('Phoenix');
    });
  });

  describe('multi-airport cities (use IATA code)', () => {
    it('shows IATA code for NYC area airports', () => {
      expect(formatAirportDisplay('KJFK')).toBe('JFK');
      expect(formatAirportDisplay('KLGA')).toBe('LGA');
      expect(formatAirportDisplay('KEWR')).toBe('EWR');
    });

    it('shows IATA code for LA area airports', () => {
      expect(formatAirportDisplay('KLAX')).toBe('LAX');
      expect(formatAirportDisplay('KBUR')).toBe('BUR');
    });

    it('shows IATA code for Chicago airports', () => {
      expect(formatAirportDisplay('KORD')).toBe('ORD');
      expect(formatAirportDisplay('KMDW')).toBe('MDW');
    });

    it('shows IATA code for San Francisco Bay Area', () => {
      expect(formatAirportDisplay('KSFO')).toBe('SFO');
      expect(formatAirportDisplay('KOAK')).toBe('OAK');
    });
  });

  describe('edge cases', () => {
    it('returns ??? for null/undefined', () => {
      expect(formatAirportDisplay(null)).toBe('???');
      expect(formatAirportDisplay(undefined)).toBe('???');
    });

    it('returns original code for unknown airports', () => {
      expect(formatAirportDisplay('ZZZZ')).toBe('ZZZZ');
      expect(formatAirportDisplay('UNKNOWN')).toBe('UNKNOWN');
    });

    it('handles lowercase input', () => {
      expect(formatAirportDisplay('kbos')).toBe('Boston');
      expect(formatAirportDisplay('kjfk')).toBe('JFK');
    });
  });
});
