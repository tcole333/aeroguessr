import { useStore } from '../../../hooks/useStore';
import { selectPlaneMap } from '../selectors';

export default function PlaneListPanelContent(): JSX.Element {
  const planeMap = useStore(selectPlaneMap);
  const planes = Object.values(planeMap);

  if (planes.length === 0) {
    return <p>Scanning for nearby flights…</p>;
  }

  const handleClick = (hex: string) => {
    // Placeholder for future map interaction
    // eslint-disable-next-line no-console
    console.log('Plane selected', hex);
  };

  return (
    <ul>
      {planes.map((plane) => (
        <li key={plane.hex_ident} className="border-b border-gray-700 last:border-none">
          <button
            type="button"
            onClick={() => handleClick(plane.hex_ident)}
            className="flex w-full items-center justify-between py-2 text-left"
          >
            <span>{plane.callsign || plane.hex_ident}</span>
            <span>{plane.alt.toLocaleString()} ft</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
