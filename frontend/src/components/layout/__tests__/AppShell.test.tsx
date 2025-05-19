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

  it('keeps map flex-1 and shrinks panel on toggle', async () => {
    const { container } = render(
      <StoreProvider>
        <AppShell />
      </StoreProvider>,
    );
    const toggle = screen.getByRole('button', { name: /minimize panel/i });
    const rootDiv = container.firstElementChild as HTMLElement;
    const panelDiv = rootDiv.lastElementChild as HTMLElement;
    const mapDiv = rootDiv.firstElementChild as HTMLElement;
    expect(mapDiv).toHaveClass('flex-1');
    await userEvent.click(toggle);
    expect(panelDiv).toHaveClass('md:w-16');
    expect(mapDiv).toHaveClass('flex-1');
  });
});
