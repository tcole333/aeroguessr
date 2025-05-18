/**
 * AUTO-GENERATED FILE. DO NOT EDIT.
 * Source: docs/ws_schema.yaml
 * Generated: 2025-05-18T20:49:22.937Z
 */

import { z } from 'zod';

export const PingPongPayloadSchema = z.object({ seq: z.number().int() });
export type PingPongPayload = z.infer<typeof PingPongPayloadSchema>;

export const PingSchema = z.object({ type: z.literal('ping'), payload: PingPongPayloadSchema, ts: z.number().optional() });
export type Ping = z.infer<typeof PingSchema>;

export const PongSchema = z.object({ type: z.literal('pong'), payload: PingPongPayloadSchema, ts: z.number().optional() });
export type Pong = z.infer<typeof PongSchema>;

export const InboundMessageSchema = z.discriminatedUnion("type", [PongSchema]);
export type InboundMessage = z.infer<typeof InboundMessageSchema>;
export const OutboundMessageSchema = z.discriminatedUnion("type", [PingSchema]);
export type OutboundMessage = z.infer<typeof OutboundMessageSchema>;
