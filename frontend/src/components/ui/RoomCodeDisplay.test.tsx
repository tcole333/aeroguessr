import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RoomCodeDisplay } from './RoomCodeDisplay';
import * as connectionSlice from '../../features/connection/connectionSlice';

// Mock the store
vi.mock('../../hooks/useStore', () => ({
  useStore: vi.fn((selector) => selector({ connection: mockConnectionState, ui: mockUiState })),
}));

let mockConnectionState = {
  roomCode: 'ABCD',
};

let mockUiState = {
  retroMode: false,
};

// Mock clipboard API
const mockWriteText = vi.fn();
Object.assign(navigator, {
  clipboard: {
    writeText: mockWriteText,
  },
});

describe('RoomCodeDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConnectionState = { roomCode: 'ABCD' };
    mockUiState = { retroMode: false };
  });

  it('should display the room code', () => {
    vi.spyOn(connectionSlice, 'selectRoomCode').mockImplementation(
      (state: any) => state.connection.roomCode
    );

    render(<RoomCodeDisplay />);

    expect(screen.getByText('Room:')).toBeInTheDocument();
    expect(screen.getByText('ABCD')).toBeInTheDocument();
  });

  it('should not render for solo mode', () => {
    mockConnectionState = { roomCode: 'solo' };
    vi.spyOn(connectionSlice, 'selectRoomCode').mockImplementation(
      (state: any) => state.connection.roomCode
    );

    const { container } = render(<RoomCodeDisplay />);

    expect(container.firstChild).toBeNull();
  });

  it('should not render when no room code', () => {
    mockConnectionState = { roomCode: null };
    vi.spyOn(connectionSlice, 'selectRoomCode').mockImplementation(
      (state: any) => state.connection.roomCode
    );

    const { container } = render(<RoomCodeDisplay />);

    expect(container.firstChild).toBeNull();
  });

  it('should copy room code to clipboard on click', async () => {
    mockWriteText.mockResolvedValueOnce(undefined);
    vi.spyOn(connectionSlice, 'selectRoomCode').mockImplementation(
      (state: any) => state.connection.roomCode
    );

    render(<RoomCodeDisplay />);

    const button = screen.getByRole('button', { name: /Room code ABCD. Click to copy/i });
    fireEvent.click(button);

    expect(mockWriteText).toHaveBeenCalledWith('ABCD');

    await waitFor(() => {
      expect(screen.getByText('Copied!')).toBeInTheDocument();
    });
  });

  it('should show temporary copied message', async () => {
    mockWriteText.mockResolvedValueOnce(undefined);
    vi.spyOn(connectionSlice, 'selectRoomCode').mockImplementation(
      (state: any) => state.connection.roomCode
    );

    render(<RoomCodeDisplay />);

    const button = screen.getByRole('button');
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText('Copied!')).toBeInTheDocument();
    });

    // Wait for message to disappear
    await waitFor(() => {
      expect(screen.queryByText('Copied!')).not.toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it('should handle clipboard error gracefully', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockWriteText.mockRejectedValueOnce(new Error('Clipboard error'));
    vi.spyOn(connectionSlice, 'selectRoomCode').mockImplementation(
      (state: any) => state.connection.roomCode
    );

    render(<RoomCodeDisplay />);

    const button = screen.getByRole('button');
    fireEvent.click(button);

    await waitFor(() => {
      expect(consoleError).toHaveBeenCalledWith('Failed to copy room code:', expect.any(Error));
    });

    expect(screen.queryByText('Copied!')).not.toBeInTheDocument();

    consoleError.mockRestore();
  });

  it('should accept custom className', () => {
    vi.spyOn(connectionSlice, 'selectRoomCode').mockImplementation(
      (state: any) => state.connection.roomCode
    );

    const { container } = render(<RoomCodeDisplay className="custom-class" />);

    expect(container.firstChild).toHaveClass('custom-class');
  });
});
