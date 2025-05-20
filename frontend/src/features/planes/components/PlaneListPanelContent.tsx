import { useStore } from '../../../hooks/useStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';
import { selectPlaneMap } from '../selectors';
import { selectHost, selectIsSolo } from '../../game/selectors';
import {
  selectNickname,
  selectConnectionStatus,
} from '../../connection/selectors';

export default function PlaneListPanelContent(): JSX.Element {
  const planeMap = useStore(selectPlaneMap);
  const planes = Object.values(planeMap);
  const host = useStore(selectHost);
  const isSolo = useStore(selectIsSolo);
  const myNick = useStore(selectNickname);
  const status = useStore(selectConnectionStatus);
  const setSelectedPlane = useStore((s) => s.game.setSelectedPlane);

  if (planes.length === 0) {
    return <p>Scanning for nearby flights…</p>;
  }

  const handleClick = (hex: string) => {
    const isHost = !isSolo && host && myNick === host;
    if (!isHost || status !== 'connected') return;
    setSelectedPlane(hex);
    try {
      webSocketClient.send({ type: 'selectPlane', payload: { hex } });
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(err);
    }
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
