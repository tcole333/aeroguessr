import AppShell from './components/layout/AppShell';
import { StoreProvider } from './store/createRootStore';

export default function App(): JSX.Element {
  return (
    <StoreProvider>
      <AppShell />
    </StoreProvider>
  );
}
