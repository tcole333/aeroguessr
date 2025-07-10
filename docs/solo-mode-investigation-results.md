# Solo Mode Investigation Results

## Summary
Solo mode is partially implemented but has critical frontend issues preventing it from being functional. The backend is mostly complete and working correctly.

## Current Implementation Status

### ✅ Working Components

1. **Backend API**
   - `POST /api/v0/rooms/solo/join` endpoint works correctly
   - Creates unique solo room instances (e.g., `solo:abc123`)
   - Sets `is_solo: true` flag in room metadata
   - WebSocket connection and state sync work properly

2. **Backend WebSocket Handlers**
   - Solo mode loop implemented in `websocket_endpoint`
   - `selectPlane` message handler works for solo mode
   - `guess` message handler works and returns results
   - Proper error handling for insufficient plane data
   - Host-only commands correctly rejected in solo mode

3. **Frontend Initial Flow**
   - `StartSoloForm` component exists and works
   - API call to join solo room succeeds
   - WebSocket connection established successfully
   - State sync received and processed

4. **Integration Tests**
   - Comprehensive test in `test_solo_mode.py` passes
   - Tests full flow: join → select plane → guess → result

### ❌ Critical Issues

1. **Plane Selection UI Missing (CRITICAL)**
   - In `PlaneDetails.tsx`, `isHost` is set to `false` for solo mode
   - This prevents the plane selection button from appearing
   - Solo players cannot select planes through the UI
   - Code: `const isHost = !isSolo && host && myNick === host;`

2. **No Solo-Specific UI Logic**
   - PlaneDetails component has no solo-specific selection logic
   - Round-based UI elements shown even though solo mode has no rounds
   - Game status indicator shows confusing state for solo players

3. **Missing Immediate Guess Flow**
   - After selecting a plane, solo players should immediately see guess form
   - Currently requires host to "start round" which doesn't apply to solo

## Backend Solo Mode Flow (Working)

1. Player joins with room code "solo"
2. Backend creates unique room ID (e.g., `solo:abc123`)
3. Player connects via WebSocket
4. Player sends `selectPlane` message
5. Backend validates plane has origin/destination data
6. Backend sends `planeSelectedConfirm` with guess direction
7. Player sends `guess` message
8. Backend calculates score and sends `roundResult`
9. Player can immediately select another plane

## Frontend Issues Detail

### Issue 1: Plane Selection Button Hidden
```typescript
// PlaneDetails.tsx line 42
const isHost = !isSolo && host && myNick === host;
// This evaluates to false in solo mode, hiding selection controls
```

### Issue 2: No Solo-Specific Flow
The component needs logic like:
```typescript
const canSelectPlaneInSolo = isSolo && status === 'connected' && !isUsed;
const showSelectionControls = isHost || isSolo;
```

### Issue 3: Round-Based UI in Solo Mode
Solo mode shows round numbers and "waiting for host" states which don't apply.

## Recommended Fixes

### Priority 1: Enable Plane Selection in Solo Mode
- Modify `PlaneDetails.tsx` to show selection button for solo players
- Add `canSelectPlaneInSolo` logic
- Hide round-specific UI elements in solo mode

### Priority 2: Implement Immediate Guess Flow
- After plane selection in solo mode, immediately show guess form
- No "Start Round" button needed
- Track selected plane in component state for solo mode

### Priority 3: Improve Solo Mode UI/UX
- Hide irrelevant UI elements (round counter, host controls)
- Add solo-specific instructions
- Show running score more prominently
- Clear feedback after each guess

### Priority 4: Add Solo Mode Features
- Implement a "streak counter" for consecutive correct guesses
- Add time-based scoring bonuses
- Show personal best scores
- Add difficulty modes (hide more/less information)

## Code References

- Backend solo handling: `backend/routes/rooms.py:386-528`
- Frontend plane details: `frontend/src/features/planes/components/PlaneDetails.tsx`
- Solo form: `frontend/src/features/game-setup/components/StartSoloForm.tsx`
- Integration test: `tests/integration/test_solo_mode.py`

## Conclusion

Solo mode backend is fully functional but the frontend prevents users from playing. The main issue is that the plane selection UI is hidden for solo players. With relatively small frontend changes, solo mode could be fully operational.
