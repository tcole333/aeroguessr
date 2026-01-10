import { useEffect, useMemo, useRef } from 'react';
import { useStore } from '../../../hooks/useStore';
import { selectPlaneMap } from '../selectors';
import { selectSelectedPlane, selectRound, selectUsedPlanes } from '../../game/selectors';
import { selectExpandedPlane, selectRetroMode } from '../../ui/selectors';
import PlaneDetails from './PlaneDetails';

const ALT_TREND_THRESHOLD = 50;

const getAltitudeTrend = (altV?: number) => {
  if (altV == null) return { symbol: '•', className: 'text-retro-text-light' };
  if (altV > ALT_TREND_THRESHOLD) return { symbol: '▲', className: 'text-retro-success' };
  if (altV < -ALT_TREND_THRESHOLD) return { symbol: '▼', className: 'text-retro-primary' };
  return { symbol: '•', className: 'text-retro-text-light' };
};

export default function PlaneListPanelContent(): JSX.Element {
  const planeMap = useStore(selectPlaneMap);
  const selectedPlane = useStore(selectSelectedPlane);
  const round = useStore(selectRound);
  const usedPlanes = useStore(selectUsedPlanes);
  const expandedPlane = useStore(selectExpandedPlane);
  const retroMode = useStore(selectRetroMode);
  const setExpandedPlane = useStore((s) => s.ui.setExpandedPlane);
  const previousRoundState = useRef<string | null>(round?.state ?? null);

  // Sort planes: selected first, used last, others in between
  const planes = useMemo(() => {
    const planesList = Object.values(planeMap);
    return planesList.sort((a, b) => {
      // Selected plane always first
      if (a.hex_ident === selectedPlane) return -1;
      if (b.hex_ident === selectedPlane) return 1;

      // Used planes go to bottom
      const aUsed = usedPlanes.has(a.hex_ident);
      const bUsed = usedPlanes.has(b.hex_ident);
      if (aUsed && !bUsed) return 1;
      if (!aUsed && bUsed) return -1;

      return 0; // Keep original order within groups
    });
  }, [planeMap, selectedPlane, usedPlanes]);

  const handlePlaneClick = (hex: string) => {
    setExpandedPlane(expandedPlane === hex ? null : hex);
  };

  const handleCloseDetails = () => {
    setExpandedPlane(null);
  };

  useEffect(() => {
    const prevState = previousRoundState.current;
    const currentState = round?.state ?? null;
    if (prevState === 'guessing' && currentState !== 'guessing') {
      if (expandedPlane && usedPlanes.has(expandedPlane)) {
        setExpandedPlane(null);
      }
    }
    previousRoundState.current = currentState;
  }, [expandedPlane, round?.state, setExpandedPlane, usedPlanes]);

  if (planes.length === 0) {
    return (
      <p className={retroMode ? 'text-retro-text-muted p-4 font-display' : 'text-gray-400 p-4'}>
        {retroMode ? 'SCANNING FOR DEPARTURES...' : 'Scanning for nearby flights…'}
      </p>
    );
  }

  // Retro departure board row
  if (retroMode) {
    return (
      <div>
        {/* Header row - departure board style with clean monospace labels */}
        <div
          className="grid grid-cols-[1fr_auto] items-center px-4 py-2 border-b border-retro-border bg-retro-panel-dark text-xs uppercase tracking-[0.2em] text-retro-sage"
        >
          <span>FLIGHT</span>
          <span className="text-right">ALTITUDE</span>
        </div>
        <ul>
          {planes.map((plane) => {
            const isSelected = selectedPlane === plane.hex_ident;
            const isRoundActive = round?.state === 'guessing' && round?.hex === plane.hex_ident;
            const isExpanded = expandedPlane === plane.hex_ident;
            const isUsed = usedPlanes.has(plane.hex_ident);
            const altitudeTrend = getAltitudeTrend(plane.alt_v);

            // Build status classes
            let statusClasses = 'departure-row';
            if (isRoundActive) {
              statusClasses += ' border-l-4 border-retro-primary-bright bg-retro-panel';
            } else if (isSelected) {
              statusClasses += ' border-l-4 border-retro-primary bg-retro-panel';
            } else if (isUsed) {
              statusClasses += ' opacity-60 border-l-4 border-retro-border';
            }

            return (
              <li key={plane.hex_ident} className={`border-b-2 border-retro-border last:border-none ${statusClasses}`}>
                <button
                  type="button"
                  onClick={() => handlePlaneClick(plane.hex_ident)}
                  className={`grid w-full grid-cols-[1fr_auto] items-center gap-4 py-3 px-4 text-left transition-all hover:bg-retro-panel-dark ${
                    isExpanded ? 'bg-retro-panel' : ''
                  }`}
                >
                  <div className="flex items-center gap-4">
                    <div>
                      <div className="font-splitflap text-base text-retro-led uppercase tracking-wider">
                        {(plane.callsign || plane.hex_ident).toUpperCase()}
                      </div>
                      <div className="text-xs font-display text-retro-text-muted tracking-widest">
                        {plane.hex_ident}
                      </div>
                    </div>
                    {/* Status badges - clean monospace */}
                    {isRoundActive && (
                      <span
                        className="text-xs uppercase tracking-widest text-retro-primary animate-glow-pulse"
                      >
                        ● ACTIVE
                      </span>
                    )}
                    {isSelected && !isRoundActive && (
                      <span
                        className="text-xs uppercase tracking-widest text-retro-primary"
                      >
                        ✓ SELECTED
                      </span>
                    )}
                    {isUsed && !isRoundActive && (
                      <span
                        className="text-xs uppercase tracking-widest text-retro-text-muted"
                      >
                        DEPARTED
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-end gap-2 tabular-nums">
                    <span className={`text-xs ${altitudeTrend.className}`} aria-hidden="true">
                      {altitudeTrend.symbol}
                    </span>
                    <span className="font-splitflap text-retro-led tracking-wider">
                      {plane.alt.toLocaleString()}
                    </span>
                    <span
                      className="text-xs text-retro-text-muted"
                    >
                      FT
                    </span>
                    <span className={`text-retro-text-light transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                      ▾
                    </span>
                  </div>
                </button>
                {isExpanded && (
                  <PlaneDetails hex={plane.hex_ident} onClose={handleCloseDetails} />
                )}
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  // Original non-retro version
  return (
    <div>
      <ul>
        {planes.map((plane) => {
          const isSelected = selectedPlane === plane.hex_ident;
          const isRoundActive = round?.state === 'guessing' && round?.hex === plane.hex_ident;
          const isExpanded = expandedPlane === plane.hex_ident;
          const isUsed = usedPlanes.has(plane.hex_ident);

          return (
            <li key={plane.hex_ident} className="border-b border-gray-700 last:border-none">
              <button
                type="button"
                onClick={() => handlePlaneClick(plane.hex_ident)}
                className={`flex w-full items-center justify-between py-3 px-4 text-left transition-colors hover:bg-gray-700 ${
                  isSelected ? 'bg-blue-900 border-l-4 border-blue-400' : ''
                } ${
                  isRoundActive ? 'bg-green-900 border-l-4 border-green-400' : ''
                } ${
                  isUsed && !isRoundActive ? 'bg-gray-800 border-l-4 border-gray-500 opacity-60' : ''
                } ${
                  isExpanded ? 'bg-gray-700' : ''
                }`}
              >
                <div className="flex items-center space-x-3">
                  <div>
                    <div className="text-white font-medium">
                      {plane.callsign || plane.hex_ident}
                    </div>
                    <div className="text-sm text-gray-400">
                      {plane.hex_ident}
                    </div>
                  </div>
                  {isSelected && (
                    <div className="text-blue-400 text-sm">
                      ✓ Selected
                    </div>
                  )}
                  {isRoundActive && (
                    <div className="text-green-400 text-sm animate-pulse">
                      ● Active
                    </div>
                  )}
                  {isUsed && !isRoundActive && (
                    <div className="text-gray-400 text-sm">
                      ✓ Used
                    </div>
                  )}
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-white">{plane.alt.toLocaleString()} ft</span>
                  <span className={`text-gray-400 transition-transform ${
                    isExpanded ? 'rotate-180' : ''
                  }`}>
                    ▼
                  </span>
                </div>
              </button>
              {isExpanded && (
                <PlaneDetails hex={plane.hex_ident} onClose={handleCloseDetails} />
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
