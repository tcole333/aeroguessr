import React, { useState, useRef, useEffect, useCallback } from 'react';
import type { AirportAutocompleteProps, Airport } from './types';
import { useAirportSearch } from './hooks/useAirportSearch';
import { useDebounce } from './hooks/useDebounce';

const DEBOUNCE_DELAY = 150; // milliseconds

export const AirportAutocomplete: React.FC<AirportAutocompleteProps> = ({
  value,
  onChange,
  onSelect,
  placeholder = 'Enter airport name or code',
  disabled = false,
  className = '',
  id,
  name,
  required = false,
  autoFocus = false,
  'aria-label': ariaLabel,
  'aria-describedby': ariaDescribedBy,
}) => {
  const [inputValue, setInputValue] = useState(value);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [hasInteracted, setHasInteracted] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);

  const { results, isLoading, search, clearResults } = useAirportSearch();
  const debouncedSearchTerm = useDebounce(inputValue, DEBOUNCE_DELAY);

  // Generate unique IDs for accessibility
  const inputId = id || `airport-input-${Math.random().toString(36).substr(2, 9)}`;
  const listboxId = `${inputId}-listbox`;
  const activeDescendantId = activeIndex >= 0 ? `${inputId}-option-${activeIndex}` : undefined;

  // Effect to perform search when debounced value changes
  useEffect(() => {
    if (debouncedSearchTerm && hasInteracted) {
      search(debouncedSearchTerm);
      setIsOpen(true);
      setActiveIndex(-1);
    } else {
      clearResults();
      setIsOpen(false);
    }
  }, [debouncedSearchTerm, search, clearResults, hasInteracted]);

  // Sync external value changes
  useEffect(() => {
    setInputValue(value);
  }, [value]);


  // Handle input change
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setInputValue(newValue);
    setHasInteracted(true);
    onChange(newValue);
  }, [onChange]);

  // Handle airport selection
  const handleSelectAirport = useCallback((airport: Airport) => {
    const code = airport.iata || airport.icao;
    setInputValue(code);
    onChange(code);
    onSelect?.(airport);
    setIsOpen(false);
    setActiveIndex(-1);
    inputRef.current?.focus();
  }, [onChange, onSelect]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || results.length === 0) {
      if (e.key === 'ArrowDown' && results.length > 0) {
        e.preventDefault();
        setIsOpen(true);
        setActiveIndex(0);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setActiveIndex(prev => (prev < results.length - 1 ? prev + 1 : prev));
        break;

      case 'ArrowUp':
        e.preventDefault();
        setActiveIndex(prev => (prev > 0 ? prev - 1 : -1));
        break;

      case 'Enter':
        e.preventDefault();
        if (activeIndex >= 0 && activeIndex < results.length) {
          handleSelectAirport(results[activeIndex]);
        }
        break;

      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setActiveIndex(-1);
        break;

      case 'Tab':
        // Let tab work naturally but close dropdown
        setIsOpen(false);
        break;
    }
  }, [isOpen, results, activeIndex, handleSelectAirport]);

  // Handle click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        !inputRef.current?.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Scroll active item into view
  useEffect(() => {
    if (activeIndex >= 0 && listboxRef.current) {
      const activeElement = listboxRef.current.querySelector(`#${inputId}-option-${activeIndex}`);
      activeElement?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [activeIndex, inputId]);

  // Clear button handler
  const handleClear = useCallback(() => {
    setInputValue('');
    onChange('');
    clearResults();
    setIsOpen(false);
    setActiveIndex(-1);
    setHasInteracted(false);
    inputRef.current?.focus();
  }, [onChange, clearResults]);

  const showClearButton = inputValue && !disabled;

  return (
    <div className={`relative ${className}`}>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          id={inputId}
          name={name}
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (results.length > 0) {
              setIsOpen(true);
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          required={required}
          autoFocus={autoFocus}
          autoComplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-activedescendant={activeDescendantId}
          aria-label={ariaLabel}
          aria-describedby={ariaDescribedBy}
          className={`
            w-full px-3 py-2 pr-10
            border border-gray-300 dark:border-gray-600
            rounded-md shadow-sm
            bg-white dark:bg-gray-800
            text-gray-900 dark:text-gray-100
            placeholder-gray-400 dark:placeholder-gray-500
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500
            disabled:bg-gray-100 dark:disabled:bg-gray-700
            disabled:cursor-not-allowed
            transition-colors duration-200
          `}
        />

        {/* Clear button */}
        {showClearButton && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors"
            aria-label="Clear input"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {/* Dropdown */}
      {isOpen && !isLoading && results.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-lg max-h-60 overflow-auto"
        >
          <ul
            ref={listboxRef}
            id={listboxId}
            role="listbox"
            aria-label="Airport suggestions"
            className="py-1"
          >
            {results.map((airport, index) => {
              const isActive = index === activeIndex;
              const optionId = `${inputId}-option-${index}`;

              return (
                <li
                  key={`${airport.iata}-${airport.icao}`}
                  id={optionId}
                  role="option"
                  aria-selected={isActive}
                  onClick={() => handleSelectAirport(airport)}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`
                    px-3 py-2 cursor-pointer transition-colors duration-150
                    ${isActive
                      ? 'bg-blue-100 dark:bg-gray-700 text-blue-900 dark:text-blue-100'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100'
                    }
                  `}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">
                      {airport.iata || airport.icao}
                    </span>
                    <span className="text-sm text-gray-500 dark:text-gray-400 ml-2">
                      {airport.municipality}, {airport.country}
                    </span>
                  </div>
                  <div className="text-sm text-gray-600 dark:text-gray-300">
                    {airport.name}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Loading indicator */}
      {isOpen && isLoading && (
        <div className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-lg p-3 text-center text-gray-500 dark:text-gray-400">
          Loading airports...
        </div>
      )}

      {/* No results message */}
      {isOpen && !isLoading && hasInteracted && debouncedSearchTerm && results.length === 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-lg p-3 text-center text-gray-500 dark:text-gray-400">
          No airports found
        </div>
      )}
    </div>
  );
};
