import { useStore } from '../../../hooks/useStore';
import { selectPlaneMap } from '../selectors';
import { selectSelectedPlane, selectRound, selectUsedPlanes } from '../../game/selectors';
import { selectExpandedPlane } from '../../ui/selectors';
import PlaneDetails from './PlaneDetails';

export default function PlaneListPanelContent(): JSX.Element {
  const planeMap = useStore(selectPlaneMap);
  const planes = Object.values(planeMap);
  const selectedPlane = useStore(selectSelectedPlane);
  const round = useStore(selectRound);
  const usedPlanes = useStore(selectUsedPlanes);
  const expandedPlane = useStore(selectExpandedPlane);
  const setExpandedPlane = useStore((s) => s.ui.setExpandedPlane);

  if (planes.length === 0) {
    return <p className="text-gray-400 p-4">Scanning for nearby flights…</p>;
  }

  const handlePlaneClick = (hex: string) => {
    setExpandedPlane(expandedPlane === hex ? null : hex);
  };

  const handleCloseDetails = () => {
    setExpandedPlane(null);
  };

  return (
    <div>
      <ul>
        {planes.map((plane) => {
          const isSelected = selectedPlane === plane.hex_ident;
          const isRoundActive = round?.state === 'guessing' && round?.hex === plane.hex_ident;
          const isExpanded = expandedPlane === plane.hex_ident;
          const isUsed = usedPlanes.has(plane.hex_ident);

          // Debug logging for the active round plane
          if (round?.hex === plane.hex_ident) {
            console.log(`[PlaneList:${plane.hex_ident}] isExpanded:`, isExpanded, 'expandedPlane:', expandedPlane);
            console.log(`[PlaneList:${plane.hex_ident}] isRoundActive:`, isRoundActive);
          }

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
