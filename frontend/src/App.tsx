import AppShell from './components/layout/AppShell';
import { StoreProvider } from './store/createRootStore';
import HomePage from './pages/HomePage';
import { useStore } from './hooks/useStore';
import { selectCurrentView } from './features/ui/selectors';

export function InnerApp(): JSX.Element {
  const currentView = useStore(selectCurrentView);
  return currentView === 'home' ? <HomePage /> : <AppShell />;
}

export default function App(): JSX.Element {
  return (
    <StoreProvider>
      <InnerApp />
    </StoreProvider>
  );
}
