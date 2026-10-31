import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PlaneDetails from '../PlaneDetails';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';
import type { PlaneState, RouteHint } from '../../../common/types';
import { webSocketClient } from '../../../../hooks/useWebSocketManager';

const DEPARTING_BOS: RouteHint = {
  guess_direction: 'destination',
  known_airport: 'KBOS',
  eligible: true,
};
const ARRIVING_BOS: RouteHint = { guess_direction: 'origin', known_airport: 'KBOS', eligible: true };
const OVERFLIGHT: RouteHint = { guess_direction: null, known_airport: null, eligible: false };

function makePlane(hex: string, routeHint: RouteHint | undefined, alt = 10000): PlaneState {
  return {
    hex_ident: hex,
    lat: 42.3656,
    lon: -71.0096,
    alt,
    lat_v: 0,
    lon_v: 0,
    alt_v: 0,
    last_update_ts: 1,
    trail: [],
    route_hint: routeHint,
  };
}

function setup(
  plane: PlaneState,
  { host = 'Me', connected = true, isSolo = true } = {},
) {
  const store = createRootStore();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();

  // Add the plane to the store
  store.getState().planes.upsertPlanes([plane]);

  store.setState((s) => {
    s.game.hostNickname = host;
    s.game.isSolo = isSolo;
    s.connection.nickname = 'Me';
    s.connection.playerNickname = 'Me';
  });
  if (connected) {
    store.getState().connection.setStatus('connected');
  }
  const onClose = vi.fn();
  const utils = render(
    <StoreContext.Provider value={store}>
      <PlaneDetails hex={plane.hex_ident} onClose={onClose} />
    </StoreContext.Provider>,
  );
  return { store, onClose, ...utils };
}

/** The value shown under the Origin or Dest label. */
function routeCell(label: 'Origin' | 'Dest'): string | null | undefined {
  return screen.getByText(label).nextElementSibling?.textContent;
}

function queryStartButton() {
  return screen.queryByRole('button', { name: /start round with this flight/i });
}

describe('PlaneDetails', () => {
  describe('plane selection', () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    it.each([
      ['a departure from', DEPARTING_BOS],
      ['an arrival at', ARRIVING_BOS],
    ])('offers %s the monitored airport for a round', (_label, routeHint) => {
      setup(makePlane('eligible_plane', routeHint));

      expect(queryStartButton()).toBeEnabled();
    });

    it('does not offer an overflight', () => {
      setup(makePlane('overhead_plane', OVERFLIGHT));

      expect(queryStartButton()).not.toBeInTheDocument();
    });

    it('does not offer a plane the server would reject', () => {
      setup(makePlane('unplayable_plane', { ...DEPARTING_BOS, eligible: false }));

      expect(queryStartButton()).not.toBeInTheDocument();
    });

    it('does not offer a plane without a route hint', () => {
      setup(makePlane('unknown_route_plane', undefined));

      expect(queryStartButton()).not.toBeInTheDocument();
    });

    it('starts the round once the server confirms the selection', async () => {
      const { store } = setup(makePlane('picked_plane', DEPARTING_BOS));
      const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
      await userEvent.click(screen.getByRole('button', { name: /start round with this flight/i }));

      act(() => store.getState().game.setSelectedPlane('picked_plane'));

      expect(sendSpy.mock.calls.map(([msg]) => msg.type)).toEqual(['selectPlane', 'startRound']);
      sendSpy.mockRestore();
    });

    it('does not start the round before the server confirms the selection', () => {
      vi.useFakeTimers();
      setup(makePlane('refused_plane', DEPARTING_BOS));
      const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
      fireEvent.click(screen.getByRole('button', { name: /start round with this flight/i }));

      // A refused selection never confirms; nothing else may follow it
      act(() => vi.advanceTimersByTime(1000));

      expect(sendSpy.mock.calls.map(([msg]) => msg.type)).toEqual(['selectPlane']);
      sendSpy.mockRestore();
    });
  });

  describe('route display', () => {
    it('shows the monitored origin and hides the destination of a departure', () => {
      setup(makePlane('departing_plane', DEPARTING_BOS));

      expect([routeCell('Origin'), routeCell('Dest')]).toEqual(['BOSTON', '???']);
    });

    it('shows the monitored destination and hides the origin of an arrival', () => {
      setup(makePlane('arriving_plane', ARRIVING_BOS));

      expect([routeCell('Origin'), routeCell('Dest')]).toEqual(['???', 'BOSTON']);
    });

    it('shows neither end of an overflight', () => {
      setup(makePlane('overhead_plane', OVERFLIGHT, 35000));

      expect([routeCell('Origin'), routeCell('Dest')]).toEqual(['???', '???']);
    });

    it('still shows flight data for an overflight', () => {
      setup(makePlane('overhead_data', OVERFLIGHT, 35000));

      expect(screen.getByText(/overhead_data/i)).toBeInTheDocument();
      expect(screen.getByText(/35,000/)).toBeInTheDocument();
    });
  });

  describe('revealed answer', () => {
    const roundStart = {
      hex: 'played_plane',
      timeout_s: 30,
      direction: 'destination',
      round_number: 1,
    };
    const roundResult = {
      hex: 'played_plane',
      next_host_nickname: null,
      results: [
        {
          nickname: 'Me',
          guess: 'LGA',
          correct_code: 'KJFK',
          score_awarded: 0,
          current_total_score: 0,
        },
      ],
    };

    function setupPlayedPlane() {
      return setup(makePlane('played_plane', DEPARTING_BOS));
    }

    it('keeps the guessed end hidden during the round', () => {
      const { store } = setupPlayedPlane();
      act(() => store.getState().game.setRoundStart(roundStart));

      expect(routeCell('Dest')).toBe('???');
    });

    it('shows the guessed end once the round result reveals it', () => {
      const { store } = setupPlayedPlane();
      act(() => {
        store.getState().game.setRoundStart(roundStart);
        store.getState().game.setRoundResult(roundResult);
      });

      expect([routeCell('Origin'), routeCell('Dest')]).toEqual(['BOSTON', 'JFK']);
    });

    it('hides a revealed answer again when a new round starts on the plane', () => {
      const { store } = setupPlayedPlane();
      act(() => {
        store.getState().game.setRoundStart(roundStart);
        store.getState().game.setRoundResult(roundResult);
        store.getState().game.setRoundStart({ ...roundStart, round_number: 2 });
      });

      expect(routeCell('Dest')).toBe('???');
    });

    it("does not show a revealed answer as the unknown end of the plane's next leg", () => {
      const { store } = setupPlayedPlane();
      act(() => {
        store.getState().game.setRoundStart(roundStart);
        store.getState().game.setRoundResult(roundResult);
        store.getState().planes.upsertPlanes([makePlane('played_plane', ARRIVING_BOS)]);
      });

      expect([routeCell('Origin'), routeCell('Dest')]).toEqual(['???', 'BOSTON']);
    });

    it('forgets a revealed answer once the plane leaves the map', () => {
      const { store } = setupPlayedPlane();
      act(() => {
        store.getState().game.setRoundStart(roundStart);
        store.getState().game.setRoundResult(roundResult);
        store.getState().planes.removePlanes(['played_plane']);
        store.getState().planes.upsertPlanes([makePlane('played_plane', DEPARTING_BOS)]);
      });

      expect(routeCell('Dest')).toBe('???');
    });

    it('keeps a skipped plane hidden when the next round reveals another plane', () => {
      const { store } = setupPlayedPlane();
      act(() => {
        store.getState().game.setRoundStart(roundStart);
        store.getState().game.applyDelta({
          round: { state: 'waiting_for_selection', round_number: 1 },
        });
        store.getState().game.setRoundStart({ ...roundStart, hex: 'next_plane', round_number: 2 });
        store.getState().game.setRoundResult({ ...roundResult, hex: 'next_plane' });
      });

      expect(routeCell('Dest')).toBe('???');
    });
  });

  describe('guess form', () => {
    const roundPlane = makePlane('round_plane', ARRIVING_BOS);

    function setupDuringRound() {
      const result = setup(roundPlane);
      act(() => {
        result.store.getState().game.setRoundStart({
          hex: roundPlane.hex_ident,
          timeout_s: 30,
          direction: 'origin',
          round_number: 1,
        });
      });
      return result;
    }

    it('does not send a code that is not in the airport dataset', async () => {
      setupDuringRound();
      const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});

      await userEvent.type(screen.getByLabelText(/airport code/i), 'ab1');
      await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));

      expect(screen.getByText(/unknown airport code 'AB1'/i)).toBeInTheDocument();
      expect(sendSpy).not.toHaveBeenCalled();
      sendSpy.mockRestore();
    });

    it('sends a known IATA code', async () => {
      setupDuringRound();
      const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});

      await userEvent.type(screen.getByLabelText(/airport code/i), 'jfk');
      await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));

      expect(sendSpy).toHaveBeenCalledWith({ type: 'guess', payload: { airport_code: 'JFK' } });
      sendSpy.mockRestore();
    });

    it('shows the server refusing a guess and lets the player guess again', async () => {
      const { store } = setupDuringRound();
      const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
      await userEvent.type(screen.getByLabelText(/airport code/i), 'jfk');
      await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));

      act(() => store.getState().game.setGuessRejection("Unknown airport code 'JFK'."));

      expect(screen.getByRole('alert')).toHaveTextContent("Unknown airport code 'JFK'.");
      expect(screen.getByRole('button', { name: /submit guess/i })).toBeEnabled();
      sendSpy.mockRestore();
    });
  });
});
