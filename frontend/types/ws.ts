import { z } from 'zod';

/**
 * Minimal WebSocket message schemas used in tests and core infrastructure.
 * In a full implementation this file is generated via `pnpm gen:schema`.
 */

export const PingSchema = z.object({
  type: z.literal('ping'),
  ts: z.number().optional(),
});
export type Ping = z.infer<typeof PingSchema>;

export const PongSchema = z.object({
  type: z.literal('pong'),
  ts: z.number().optional(),
});
export type Pong = z.infer<typeof PongSchema>;

export const InboundMessageSchema = z.discriminatedUnion('type', [
  PongSchema,
]);
export type InboundMessage = z.infer<typeof InboundMessageSchema>;

export const OutboundMessageSchema = z.discriminatedUnion('type', [
  PingSchema,
]);
export type OutboundMessage = z.infer<typeof OutboundMessageSchema>;

export function assertWsMessage(data: unknown): InboundMessage {
  return InboundMessageSchema.parse(data);
}
