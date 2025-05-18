import { InboundMessageSchema, type InboundMessage } from '../../types/ws';

export function assertWsMessage(raw: unknown): InboundMessage | null {
  let parsed: unknown;
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      console.error('Invalid JSON received via WebSocket', err);
      return null;
    }
  } else {
    parsed = raw;
  }
  const result = InboundMessageSchema.safeParse(parsed);
  if (!result.success) {
    console.error('Invalid WebSocket message', result.error.issues);
    return null;
  }
  return result.data;
}
