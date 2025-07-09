import AppShell from './components/layout/AppShell';
import { StoreProvider } from './store/createRootStore';
import HomePage from './pages/HomePage';
import { useStore } from './hooks/useStore';
import { selectCurrentView } from './features/ui/selectors';
import { useAutoRejoin } from './hooks/useAutoRejoin';

export function InnerApp(): JSX.Element {
  const currentView = useStore(selectCurrentView);

  // Handle automatic rejoin logic on app startup
  useAutoRejoin();

  return currentView === 'home' ? <HomePage /> : <AppShell />;
}

export default function App(): JSX.Element {
  return (
    <StoreProvider>
      <InnerApp />
    </StoreProvider>
  );
}
