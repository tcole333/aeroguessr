import CreateRoomForm from '../features/game-setup/components/CreateRoomForm';
import JoinRoomForm from '../features/game-setup/components/JoinRoomForm';
import StartSoloForm from '../features/game-setup/components/StartSoloForm';

export default function HomePage(): JSX.Element {
  return (
    <div className="p-4 space-y-6">
      <h1 className="text-2xl font-bold">Plane Guessing Game</h1>
      <CreateRoomForm />
      <JoinRoomForm />
      <StartSoloForm />
    </div>
  );
}
