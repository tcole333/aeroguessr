import { render } from '@testing-library/react';
import AppShell from '../AppShell';
import { StoreProvider } from '../../../store/createRootStore';

describe('AppShell', () => {
  it('renders map and panel', () => {
    const { container, getByRole } = render(
      <StoreProvider>
        <AppShell />
      </StoreProvider>,
    );
    expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
    expect(getByRole('tablist')).toBeInTheDocument();
  });
});
