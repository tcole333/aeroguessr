import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PlaneListPanelContent from '../PlaneListPanelContent';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';
import type { PlaneState } from '../../../common/types';

function setup(planes: PlaneState[] = []) {
  const store = createRootStore();
  if (planes.length > 0) {
    store.getState().planes.upsertPlanes(planes);
  }
  return render(
    <StoreContext.Provider value={store}>
      <PlaneListPanelContent />
    </StoreContext.Provider>,
  );
}

describe('PlaneListPanelContent', () => {
  it('renders plane items and handles click', async () => {
    const plane: PlaneState = {
      hex_ident: 'abc',
      lat: 0,
      lon: 0,
      alt: 1000,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [],
    };
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    setup([plane]);
    const item = screen.getByRole('button', { name: /abc/i });
    expect(item).toBeInTheDocument();
    await userEvent.click(item);
    expect(logSpy).toHaveBeenCalledWith('Plane selected', 'abc');
    logSpy.mockRestore();
  });

  it('shows placeholder when no planes', () => {
    setup();
    expect(screen.getByText(/scanning for nearby flights/i)).toBeInTheDocument();
  });
});
