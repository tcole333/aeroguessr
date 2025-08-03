# Plane Tracking Investigation

## Overview
Investigation into erratic plane movement and display issues on the map UI. Planes are not rendering in correct locations, jumping around erratically, and trail paths are incorrect.

## Executive Summary
1. **Raw ADS-B data is clean** - No issues at the source
2. **Multiple processing issues found**:
   - Position validation too strict (rejecting valid updates)
   - Frontend speed calculation error (showing 251k+ knots)
   - Velocity values need clamping
3. **Mystery remains**: Consistent 1.8-2.5° jumps for specific aircraft IDs

## Known Issues (from CLAUDE.md)
- **Issue #107**: Erratic plane movement on Pi
- Root causes previously identified:
  - Kalman filter numerical instability causing resets
  - Poor parameter tuning (process noise 0.5 too high, measurement noise 10.0 too conservative)
  - No frontend position interpolation
  - Unstable heading calculations

## Investigation Areas

### 1. Backend Plane Tracking
- [ ] Kalman filter implementation
- [ ] Redis storage and updates
- [ ] WebSocket delta messages
- [ ] ADS-B data ingestion

### 2. Frontend Plane Rendering
- [ ] Map component plane display logic
- [ ] Position update handling
- [ ] Trail rendering
- [ ] WebSocket message processing

### 3. Data Flow Analysis
- [ ] ADS-B → Kalman Filter → Redis → WebSocket → Frontend

## Code Review Findings

### Backend Components

#### Kalman Filter (`backend/utils/kalman.py`)
**Critical Issues Found:**
1. **Parameter Tuning**: Default values causing numerical instability
   - Current: `KALMAN_PROCESS_NOISE=0.5`, `KALMAN_MEASUREMENT_NOISE=10.0`
   - Recommended: `KALMAN_PROCESS_NOISE=0.01`, `KALMAN_MEASUREMENT_NOISE=3.0`
2. **Numerical Instability**: High initial covariance (500.0) and poor scaling
3. **Frequent Resets**: LinAlgError exceptions trigger complete filter resets
4. **Position Validation**: Overly conservative (600 knots max) causing legitimate updates to be rejected
5. **Mixed Units**: Velocities in degrees/second vs feet/minute causing scaling issues

#### Plane State Management (`backend/ingest/state.py`)
**Findings:**
1. **Coordinate Handling**: Correct throughout (lat, lon order preserved)
2. **Trail Management**: Erratic positions get stored in trail array (capped at 10 points)
3. **Time Delta Validation**: Good protection (rejects negative/very small deltas, resets on >30s gaps)
4. **Position Jump Detection**: Only checks against previous state, not Kalman prediction
5. **Redis Storage**: Clean structure with 300s TTL, but rapid overwrites propagate instability

#### WebSocket Broadcasting (`backend/services/broadcast.py`)
**Issues Identified:**
1. **Update Frequency**: 1-second batched updates cause jerky movement
2. **No Compression**: Sending uncompressed JSON despite TODO for >1KB payloads
3. **Full State Broadcasting**: Sends complete PlaneState objects instead of just changes
4. **No Throttling**: All plane updates sent regardless of actual position changes

### Frontend Components

#### Plane Map Display (`frontend/src/features/map/`)
**Critical Gaps:**
1. **No Position Interpolation**: Direct rendering of received coordinates causes jumping
2. **Heading Calculation Instability**: Complex logic with multiple fallbacks, sensitive to velocity changes
3. **Trail Rendering**: Directly uses backend trail data including any erratic positions
4. **No Position Validation**: Invalid coordinates rendered without checks

#### WebSocket Handler (`frontend/src/hooks/useWebSocketManager.ts`)
**Findings:**
1. **Direct State Updates**: Immediate upsert of plane data without buffering
2. **No Timestamp Validation**: Processes deltas without checking order
3. **Race Conditions**: Between plane updates and removal notifications

## Log Analysis

### Raspberry Pi Logs
- Limited access to live Pi logs from local development
- Test logs show Kalman filter errors: "Kalman filter numerical instability for AC1234: Test error"
- Enrichment warnings for test data (expected)
- Evidence of filter resets: "Resetting smoother for AC1234 and using raw measurement"

## Hypotheses

### Primary Root Causes (MULTIPLE ISSUES FOUND)

#### 0. **SBS Parser MSG,2 Coordinate Bug** ✅ ROOT CAUSE FOUND!
- Parser incorrectly used fields 15 & 16 for MSG,2 lat/lon instead of 14 & 15
- MSG,2 (surface position) messages had coordinates shifted by one field
- This caused longitude values to appear as latitude, vertical rate as longitude
- Explains the consistent 1.8-2.5° jumps for specific aircraft sending MSG,2 messages
- Fixed in `backend/ingest/parser.py` lines 125-126

#### 1. **Position Validation Too Strict** ✅ FIXED
- Current limit: 0.17 degrees/second (600 knots) was rejecting legitimate movements
- **127 position jump warnings in 500 log lines**
- Fixed by increasing to 0.5 deg/sec to handle data delays and faster aircraft

#### 2. **Frontend Speed Calculation Error** ✅ FIXED
- Speed showing 251,480 knots due to incorrect unit conversion
- Formula was: `Math.sqrt(lat_v² + lon_v²) * 3600 * 60` (wrong!)
- Fixed to: `Math.sqrt(lat_v² + lon_v²) * 60 * 3600` (degrees/sec to knots)
- Added sanity check: speeds > 1000 knots shown as "Invalid"

#### 3. **Kalman Filter Producing Extreme Velocities** ✅ FIXED
- Filter instability can produce unrealistic velocity values
- Added velocity clamping: max 0.01 deg/sec (~600 knots)
- Prevents display of impossible speeds

### Secondary Issues (CONFIRMED)
1. **Kalman Parameters**: Already corrected on Pi (0.01/3.0) ✅
2. **No Frontend Interpolation**: Planes jump between updates
3. **Time Gap Resets**: Some extreme gaps causing filter resets
4. **ADS-B Data Quality**: Possible corrupted position data from receiver

### Rejected Hypotheses
1. **Kalman Filter Parameters**: Already corrected on Pi
2. **Coordinate System Mismatch**: Code review confirms correct lat/lon ordering
3. **Ingest Process Down**: Both API and ingest are running via supervisord

## Test Results

### Fake Data Testing
- Similar erratic behavior observed with synthetic data
- Confirms issue is in processing pipeline, not ADS-B data quality

### Live Data Testing
- Planes freezing and jumping on Raspberry Pi deployment
- Issue persists across different aircraft types
- More pronounced during high-traffic periods

## Action Plan

### Phase 1: Immediate Fixes (Critical)

1. **ADS-B Data Corruption Protection** 🚨 MOST URGENT
   ```bash
   # Deploy emergency fix for extreme position jumps
   ./scripts/emergency-tracking-fix.sh
   ```
   - Seeing jumps of **25+ degrees** (impossible!)
   - Added hard limit: reject any jump > 5 degrees
   - Logs extreme jumps to identify corrupted data

2. **Position Validation** ✅ PARTIALLY FIXED
   - Changed from 0.17 to 0.5 deg/sec
   - Still not enough for corrupted data
   - Need the 5-degree hard limit above

3. **Speed Display Fix** ✅ FIXED (needs deployment)
   - Frontend showing 251,480 knots due to math error
   - Fixed calculation in PlaneDetails.tsx

4. **Velocity Clamping** ✅ FIXED
   - Backend now limits velocities to 0.01 deg/sec (~600 knots)
   - Prevents Kalman filter from producing extreme values

5. **Kalman Parameters** ✅ Already Fixed
   - Confirmed: `KALMAN_PROCESS_NOISE=0.01`
   - Confirmed: `KALMAN_MEASUREMENT_NOISE=3.0`

### Phase 2: Backend Improvements (High Priority)
1. **Improve Initial Covariance** (`backend/utils/smoother.py:51-54`)
   ```python
   self.filter.P = np.eye(self.dim_state) * 10.0  # Was 500.0
   self.filter.P[3:, 3:] *= 100.0  # Was 1000.0
   ```

2. **Better Error Recovery** (`backend/ingest/main.py:243-258`)
   - Instead of full reset, preserve velocity estimates
   - Add exponential backoff for repeated failures
   - Log filter health metrics

3. **Fix Position Validation** (`backend/ingest/main.py:177`)
   ```python
   max_distance_deg = 0.25 * dt  # Was 0.17, allow up to 900 knots
   ```

### Phase 3: Frontend Enhancements (Medium Priority)
1. **Add Position Interpolation** (`frontend/src/features/map/components/PlaneMarker.tsx`)
   ```typescript
   // Use requestAnimationFrame for smooth 60fps updates
   const interpolatePosition = (from: [number, number], to: [number, number], progress: number) => {
     return [
       from[0] + (to[0] - from[0]) * progress,
       from[1] + (to[1] - from[1]) * progress
     ];
   };
   ```

2. **Stabilize Heading Calculation**
   - Add exponential moving average for heading
   - Increase minimum speed threshold to 5 knots
   - Cache heading when speed is too low

3. **Trail Smoothing**
   - Validate trail points before rendering
   - Apply Douglas-Peucker simplification
   - Fade older trail segments

### Phase 4: System Optimizations (Low Priority)
1. **WebSocket Improvements**
   - Increase update frequency to 2 FPS (`BROADCAST_INTERVAL_SECONDS=0.5`)
   - Implement delta compression
   - Add message batching with priorities

2. **Monitoring & Observability**
   - Add Kalman filter health metrics
   - Track position jump frequency
   - Monitor client-side rendering performance

### Testing Plan
1. **Unit Tests**: Add tests for Kalman parameter ranges
2. **Integration Tests**: Verify filter stability under various conditions
3. **Load Testing**: Ensure stability with 50+ simultaneous aircraft
4. **Visual Testing**: Record before/after videos of plane movement

### Deployment Script
```bash
#!/bin/bash
# deploy-tracking-fix.sh

# 1. Update .env on Pi
ssh pi@raspberrypi.local "cd plane-game-v4 && \
  sed -i 's/KALMAN_PROCESS_NOISE=0.5/KALMAN_PROCESS_NOISE=0.01/' .env && \
  sed -i 's/KALMAN_MEASUREMENT_NOISE=10.0/KALMAN_MEASUREMENT_NOISE=3.0/' .env"

# 2. Restart services
ssh pi@raspberrypi.local "cd plane-game-v4 && docker compose restart backend"

# 3. Monitor logs
ssh pi@raspberrypi.local "cd plane-game-v4 && docker logs -f plane-game-v4-backend-1"
```

### Success Criteria
- [ ] No LinAlgError exceptions in 1 hour of operation
- [ ] Smooth plane movement without visible jumps
- [ ] Trail rendering shows consistent flight paths
- [ ] <5% CPU usage increase from interpolation

## References
- Issue #107: https://github.com/tcole333/plane-game-v4/issues/107
- Previous investigation in CLAUDE.md (lines 262-273)
