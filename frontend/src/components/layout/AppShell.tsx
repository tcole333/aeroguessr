import MapView from '../../features/map/components/MapView';
import SlidingPanel from './SlidingPanel';
import { useStore } from '../../hooks/useStore';
import { selectDarkMode } from '../../features/ui/selectors';

export default function AppShell(): JSX.Element {
  const darkMode = useStore(selectDarkMode);

  return (
    <div className={`h-screen w-screen flex flex-col md:flex-row bg-gray-100 dark:bg-gray-900 ${darkMode ? 'dark' : ''}`}>
      {/* Map container: takes top half on mobile, flexible width on desktop */}
      <div className="h-1/2 w-full md:flex-1 md:h-full">
        <MapView />
      </div>
      {/* Panel container: takes bottom half on mobile, fixed width on desktop */}
      <SlidingPanel />
    </div>
  );
}
