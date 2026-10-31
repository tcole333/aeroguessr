import AppShell from './components/layout/AppShell';
import { StoreProvider } from './store/createRootStore';
import HomePage from './pages/HomePage';
import { useStore } from './hooks/useStore';
import { selectCurrentView } from './features/ui/selectors';
import { useAutoRejoin } from './hooks/useAutoRejoin';
import { AppErrorBoundary } from './components/ErrorBoundary/AppErrorBoundary';
import { CrashRecoveryScreen } from './components/ErrorBoundary/CrashRecoveryScreen';
import { useLoadClientConfig } from './features/config/useLoadClientConfig';

export function InnerApp(): JSX.Element {
  const currentView = useStore(selectCurrentView);

  // Handle automatic rejoin logic on app startup
  useAutoRejoin();
  // Fetch the map's location and style now, so the game view opens without waiting
  useLoadClientConfig();

  return currentView === 'home' ? <HomePage /> : <AppShell />;
}

export default function App(): JSX.Element {
  return (
    <StoreProvider>
      <AppErrorBoundary renderFallback={(error) => <CrashRecoveryScreen error={error} />}>
        <InnerApp />
      </AppErrorBoundary>
    </StoreProvider>
  );
}
