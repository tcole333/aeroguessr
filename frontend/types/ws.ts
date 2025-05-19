/**
 * AUTO-GENERATED FILE. DO NOT EDIT.
 * Source: docs/ws_schema.yaml
 * Generated: 2025-05-18T21:50:01.178Z
 */

import { z } from 'zod';

export const PingPongPayloadSchema = z.object({ seq: z.number().int() });
export type PingPongPayload = z.infer<typeof PingPongPayloadSchema>;

export const PingSchema = z.object({ type: z.literal('ping'), payload: PingPongPayloadSchema.optional(), ts: z.number().optional() });
export type Ping = z.infer<typeof PingSchema>;

export const PongSchema = z.object({ type: z.literal('pong'), payload: PingPongPayloadSchema.optional(), ts: z.number().optional() });
export type Pong = z.infer<typeof PongSchema>;

// Additional message payloads
export const PlaneStateSchema = z.object({
  hex_ident: z.string(),
  lat: z.number(),
  lon: z.number(),
  alt: z.number(),
  lat_v: z.number(),
  lon_v: z.number(),
  alt_v: z.number(),
  last_update_ts: z.number(),
  trail: z.array(z.tuple([z.number(), z.number(), z.number()])),
  callsign: z.string().nullable().optional(),
  origin_country: z.string().nullable().optional(),
  category: z.number().nullable().optional(),
  origin: z.string().nullable().optional(),
  destination: z.string().nullable().optional(),
});
export type PlaneState = z.infer<typeof PlaneStateSchema>;

export const RoundDeltaSchema = z.object({
  state: z.string(),
  round_number: z.number().int(),
});
export type RoundDelta = z.infer<typeof RoundDeltaSchema>;

export const DeltaPayloadSchema = z.object({
  planes: z
    .object({
      updated: z.array(PlaneStateSchema).optional(),
      removed: z.array(z.string()).optional(),
    })
    .nullable()
    .optional(),
  scores: z.record(z.number()).nullable().optional(),
  round: RoundDeltaSchema.nullable().optional(),
});
export type DeltaPayload = z.infer<typeof DeltaPayloadSchema>;

export const FullRoomStateSchema = z.object({
  room_meta: z.record(z.any()).nullable(),
  players: z.record(z.any()),
});
export type FullRoomState = z.infer<typeof FullRoomStateSchema>;

export const RoundStartPayloadSchema = z.object({
  hex: z.string(),
  timeout_s: z.number().int(),
  direction: z.string(),
  round_number: z.number().int(),
});
export type RoundStartPayload = z.infer<typeof RoundStartPayloadSchema>;

export const RoundResultDetailSchema = z.object({
  nickname: z.string(),
  guess: z.string().nullable(),
  correct_code: z.string(),
  score_awarded: z.number().int(),
  current_total_score: z.number().int(),
});

export const RoundResultPayloadSchema = z.object({
  results: z.array(RoundResultDetailSchema),
  next_host_nickname: z.string().nullable(),
});
export type RoundResultPayload = z.infer<typeof RoundResultPayloadSchema>;

export const StateSyncSchema = z.object({
  type: z.literal('stateSync'),
  payload: FullRoomStateSchema,
  ts: z.number().optional(),
});
export type StateSync = z.infer<typeof StateSyncSchema>;

export const DeltaSchema = z.object({
  type: z.literal('delta'),
  payload: DeltaPayloadSchema,
  ts: z.number().optional(),
});
export type Delta = z.infer<typeof DeltaSchema>;

export const RoundStartSchema = z.object({
  type: z.literal('roundStart'),
  payload: RoundStartPayloadSchema,
  ts: z.number().optional(),
});
export type RoundStart = z.infer<typeof RoundStartSchema>;

export const RoundResultSchema = z.object({
  type: z.literal('roundResult'),
  payload: RoundResultPayloadSchema,
  ts: z.number().optional(),
});
export type RoundResult = z.infer<typeof RoundResultSchema>;

export const InboundMessageSchema = z.discriminatedUnion('type', [
  PingSchema,
  PongSchema,
  StateSyncSchema,
  DeltaSchema,
  RoundStartSchema,
  RoundResultSchema,
]);
export type InboundMessage = z.infer<typeof InboundMessageSchema>;
export const OutboundMessageSchema = z.discriminatedUnion('type', [PingSchema]);
export type OutboundMessage = z.infer<typeof OutboundMessageSchema>;
