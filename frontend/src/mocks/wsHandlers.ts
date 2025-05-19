import { ws } from "msw";

// Example mock WebSocket server using MSW's webSocket API.
// Tests can attach listeners to `mockSocket` to simulate server behaviour.
export const mockSocket = ws.link("ws://localhost:8000/ws/*");

export const webSocketHandlers = [mockSocket];
