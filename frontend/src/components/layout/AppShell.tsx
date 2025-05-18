import MapView from '../../features/map/components/MapView';
import SlidingPanel from './SlidingPanel';
import { useStore } from '../../hooks/useStore';
import { selectDarkMode } from '../../features/ui/selectors';

export default function AppShell(): JSX.Element {
  const darkMode = useStore(selectDarkMode);

  return (
    <div className={darkMode ? 'dark' : ''}>
      <div className="h-screen w-screen relative bg-gray-100 dark:bg-gray-900">
        <MapView />
        <SlidingPanel />
      </div>
    </div>
  );
}
