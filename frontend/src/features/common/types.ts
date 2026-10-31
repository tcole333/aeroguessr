export type ConnectionStatus =
  | "connected"
  | "connecting"
  | "reconnecting"
  | "disconnected"
  | "error";

export type GuessDirection = "origin" | "destination";

/**
 * The non-secret part of a plane's route, derived by the server. The end players
 * would guess is never sent before roundResult.
 */
export interface RouteHint {
  /** Which end players would guess; null when neither end is the monitored airport. */
  guess_direction: GuessDirection | null;
  /** ICAO code of the monitored end (e.g. KBOS); null for overflights. */
  known_airport: string | null;
  /** Whether the server accepts this plane for a round. */
  eligible: boolean;
}

export interface PlaneState {
  hex_ident: string;
  lat: number;
  lon: number;
  alt: number;
  lat_v: number;
  lon_v: number;
  alt_v: number;
  last_update_ts: number;
  trail: [number, number, number][];
  callsign?: string | null;
  track?: number | null;
  operator?: string | null;
  route_hint?: RouteHint | null;
}

export interface RoundDelta {
  state: string;
  round_number: number;
}

export interface DeltaPayload {
  planes?: {
    updated?: PlaneState[];
    removed?: string[];
  } | null;
  scores?: Record<string, number> | null;
  round?: RoundDelta | null;
}

export interface RoomMeta {
  host_nickname?: string;
  is_solo?: boolean;
  round_timeout_seconds?: number;
  [k: string]: unknown;
}

export interface PlayerState {
  score?: number;
  [k: string]: unknown;
}

export interface FullRoomState {
  room_meta: RoomMeta | null;
  players: Record<string, PlayerState>;
}

export interface RoundStartPayload {
  hex: string;
  timeout_s: number;
  direction: string;
  round_number: number;
}

export interface RoundResultDetail {
  nickname: string;
  guess: string | null;
  correct_code: string;
  score_awarded: number;
  current_total_score: number;
  distance_km?: number | null;
}

export interface RoundResultPayload {
  results: RoundResultDetail[];
  next_host_nickname: string | null;
  /** The plane the round was about; with correct_code, the only reveal of its answer. */
  hex?: string | null;
}
