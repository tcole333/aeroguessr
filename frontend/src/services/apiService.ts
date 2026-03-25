
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

export function resolveApiBaseUrl(
  envBaseUrl: string | undefined = import.meta.env.VITE_API_BASE_URL,
): string {
  return envBaseUrl || '/api/v0';
}

const API_BASE_URL = resolveApiBaseUrl();

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
