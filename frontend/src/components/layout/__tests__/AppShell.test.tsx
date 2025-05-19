import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

  it('expands map when panel closed', async () => {
    const { container } = render(
      <StoreProvider>
        <AppShell />
      </StoreProvider>,
    );
    const toggle = screen.getByRole('button', { name: /minimize panel/i });
    const rootDiv = container.firstElementChild as HTMLElement;
    const mapDiv = rootDiv.firstElementChild as HTMLElement;
    expect(mapDiv).toHaveClass('md:flex-1');
    await userEvent.click(toggle);
    expect(mapDiv).toHaveClass('md:w-full');
  });
});
