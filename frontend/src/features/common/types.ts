export type ConnectionStatus =
  | "connected"
  | "connecting"
  | "reconnecting"
  | "disconnected"
  | "error";

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
  origin_country?: string | null;
  category?: number | null;
  track?: number | null;
  origin?: string | null;
  destination?: string | null;
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
  code?: string;
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
}

export interface RoundResultPayload {
  results: RoundResultDetail[];
  next_host_nickname: string | null;
}
