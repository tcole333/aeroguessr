import { z } from 'zod';

const LatLonSchema = z.object({ lat: z.number(), lon: z.number() });

/** GET /api/v0/config: where this install is and how to draw its map (ClientConfig). */
export const ClientConfigSchema = z.object({
  center: LatLonSchema,
  monitored_airport: z.object({
    icao: z.string(),
    iata: z.string().nullable(),
    name: z.string().nullable(),
    position: LatLonSchema.nullable(),
  }),
  max_antenna_range_km: z.number(),
  map_style_url: z.string(),
  attributions: z.array(z.string()),
  version: z.string(),
});

export type ClientConfig = z.infer<typeof ClientConfigSchema>;
export type MonitoredAirport = ClientConfig['monitored_airport'];

export interface RoomCreateRequest {
  host_nickname: string;
  mode: 'Exact' | 'Distance';
  round_timeout_seconds: number;
}

export interface RoomCreateResponse {
  room_code: string;
  ws_url: string;
}

export interface RoomJoinRequest {
  nickname: string;
}

export interface RoomJoinResponse {
  room_code: string;
  ws_url: string;
}

async function handleResponse(res: Response): Promise<any> {
  if (!res.ok) {
    let detail = 'Request failed';
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      // ignore json parse errors
    }
    throw new Error(detail);
  }
  return res.json();
}

// Same origin by default: nginx in production, the Vite proxy in development.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v0';

export async function createRoomAPI(
  params: RoomCreateRequest,
): Promise<RoomCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/rooms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return handleResponse(res);
}

export async function joinRoomAPI(
  roomCode: string,
  params: RoomJoinRequest,
): Promise<RoomJoinResponse> {
  const res = await fetch(`${API_BASE_URL}/rooms/${roomCode}/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  return handleResponse(res);
}

export async function startSoloGameAPI(
  params: RoomJoinRequest,
): Promise<RoomJoinResponse> {
  return joinRoomAPI('solo', params);
}

/** Rejects when the request fails or the response is not a ClientConfig. */
export async function fetchClientConfig(): Promise<ClientConfig> {
  const res = await fetch(`${API_BASE_URL}/config`);
  return ClientConfigSchema.parse(await handleResponse(res));
}
