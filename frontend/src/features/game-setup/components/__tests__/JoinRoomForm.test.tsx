import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect } from 'vitest';
import JoinRoomForm from '../JoinRoomForm';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';
import * as api from '../../../../services/apiService';

describe('JoinRoomForm', () => {
  it('joins room and sets state', async () => {
    const store = createRootStore();
    // Toggle retroMode off (default is true) to test standard mode UI
    store.getState().ui.toggleRetroMode();
    vi.spyOn(api, 'joinRoomAPI').mockResolvedValue({ room_code: 'ABCD', ws_url: 'ws://j' });
    render(
      <StoreContext.Provider value={store}>
        <JoinRoomForm />
      </StoreContext.Provider>,
    );
    await userEvent.type(screen.getByLabelText(/room code/i), 'abcd');
    await userEvent.type(screen.getByLabelText(/^nickname/i), 'Jane');
    await userEvent.click(screen.getByRole('button', { name: /join/i }));
    expect(api.joinRoomAPI).toHaveBeenCalledWith('ABCD', { nickname: 'Jane' });
    expect(store.getState().connection.wsUrl).toBe('ws://j');
  });
});
