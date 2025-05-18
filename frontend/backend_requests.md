### [2025-04-27] Add `skipRound` WebSocket Action

**Context:** The PRD §3.1 step 5 allows the host to skip a round. The current `docs/ws_schema.yaml` lists `selectPlane`, `startRound`, `transferHost`, and `claimHost`, but **lacks a `skipRound` client→server message type**.

**Proposed change:**

1. Extend `docs/ws_schema.yaml`:
   - Add `skipRound` to the top-level `messages` map with an empty payload schema (or a dedicated `SkipRoundPayload` if future params needed).
2. Backend WS handler should:
   - Validate caller is current host.
   - Transition round state back to `waiting_for_selection` without scoring.
   - Broadcast `delta` with updated room state.

**Priority:** Medium – required for full host control UX but not a blocker for MVP if host can simply select a new plane.
