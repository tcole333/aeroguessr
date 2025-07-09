import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAutoRejoin } from '../useAutoRejoin';
import { useStore } from '../useStore';

// Mock the useStore hook
vi.mock('../useStore', () => ({
  useStore: vi.fn(),
}));

describe('useAutoRejoin', () => {
  const mockSetIsRejoinAttempt = vi.fn();
  const mockSetCurrentView = vi.fn();
  const mockSetError = vi.fn();
  const mockClearConnectionDetails = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    // Reset localStorage
    localStorage.clear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('should attempt rejoin when connection data exists and currentView is game', () => {
    const mockUseStore = useStore as unknown as ReturnType<typeof vi.fn>;
    mockUseStore.mockImplementation((selector) => {
      if (selector.toString().includes('roomCode')) return 'TEST';
      if (selector.toString().includes('wsUrl')) return 'ws://test/ws/TEST/player';
      if (selector.toString().includes('nickname')) return 'TestPlayer';
      if (selector.toString().includes('currentView')) return 'game';
      if (selector.toString().includes('setIsRejoinAttempt')) return mockSetIsRejoinAttempt;
      if (selector.toString().includes('setCurrentView')) return mockSetCurrentView;
      if (selector.toString().includes('setError')) return mockSetError;
      if (selector.toString().includes('clearConnectionDetails')) return mockClearConnectionDetails;
      return undefined;
    });

    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    renderHook(() => useAutoRejoin());

    expect(consoleSpy).toHaveBeenCalledWith(
      '[AutoRejoin] Attempting to rejoin room:',
      'TEST',
      'as',
      'TestPlayer'
    );
    expect(mockSetIsRejoinAttempt).toHaveBeenCalledWith(true);

    consoleSpy.mockRestore();
  });

  it('should clear connection data when on home page with stale data', () => {
    const mockUseStore = useStore as unknown as ReturnType<typeof vi.fn>;
    mockUseStore.mockImplementation((selector) => {
      if (selector.toString().includes('roomCode')) return 'TEST';
      if (selector.toString().includes('wsUrl')) return 'ws://test/ws/TEST/player';
      if (selector.toString().includes('nickname')) return 'TestPlayer';
      if (selector.toString().includes('currentView')) return 'home';
      if (selector.toString().includes('setIsRejoinAttempt')) return mockSetIsRejoinAttempt;
      if (selector.toString().includes('setCurrentView')) return mockSetCurrentView;
      if (selector.toString().includes('setError')) return mockSetError;
      if (selector.toString().includes('clearConnectionDetails')) return mockClearConnectionDetails;
      return undefined;
    });

    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    renderHook(() => useAutoRejoin());

    expect(consoleSpy).toHaveBeenCalledWith('[AutoRejoin] Clearing stale connection data');
    expect(mockClearConnectionDetails).toHaveBeenCalled();

    consoleSpy.mockRestore();
  });

  it('should not attempt rejoin when no connection data exists', () => {
    const mockUseStore = useStore as unknown as ReturnType<typeof vi.fn>;
    mockUseStore.mockImplementation((selector) => {
      if (selector.toString().includes('roomCode')) return null;
      if (selector.toString().includes('wsUrl')) return null;
      if (selector.toString().includes('nickname')) return null;
      if (selector.toString().includes('currentView')) return 'home';
      if (selector.toString().includes('setIsRejoinAttempt')) return mockSetIsRejoinAttempt;
      if (selector.toString().includes('setCurrentView')) return mockSetCurrentView;
      if (selector.toString().includes('setError')) return mockSetError;
      if (selector.toString().includes('clearConnectionDetails')) return mockClearConnectionDetails;
      return undefined;
    });

    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    renderHook(() => useAutoRejoin());

    expect(consoleSpy).not.toHaveBeenCalled();
    expect(mockSetIsRejoinAttempt).not.toHaveBeenCalled();
    expect(mockClearConnectionDetails).not.toHaveBeenCalled();

    consoleSpy.mockRestore();
  });

  it('should only run once on multiple renders', () => {
    const mockUseStore = useStore as unknown as ReturnType<typeof vi.fn>;
    mockUseStore.mockImplementation((selector) => {
      if (selector.toString().includes('roomCode')) return 'TEST';
      if (selector.toString().includes('wsUrl')) return 'ws://test/ws/TEST/player';
      if (selector.toString().includes('nickname')) return 'TestPlayer';
      if (selector.toString().includes('currentView')) return 'game';
      if (selector.toString().includes('setIsRejoinAttempt')) return mockSetIsRejoinAttempt;
      if (selector.toString().includes('setCurrentView')) return mockSetCurrentView;
      if (selector.toString().includes('setError')) return mockSetError;
      if (selector.toString().includes('clearConnectionDetails')) return mockClearConnectionDetails;
      return undefined;
    });

    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    const { rerender } = renderHook(() => useAutoRejoin());

    // Re-render the hook
    rerender();
    rerender();

    // Should only be called once despite multiple renders
    expect(consoleSpy).toHaveBeenCalledTimes(1);
    expect(mockSetIsRejoinAttempt).toHaveBeenCalledTimes(1);

    consoleSpy.mockRestore();
  });
});
