import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect } from 'vitest';
import CreateRoomForm from '../CreateRoomForm';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';
import * as api from '../../../../services/apiService';

describe('CreateRoomForm', () => {
  it('submits form and updates store', async () => {
    const store = createRootStore();
    vi.spyOn(api, 'createRoomAPI').mockResolvedValue({ room_code: 'CODE', ws_url: 'ws://c' });
    render(
      <StoreContext.Provider value={store}>
        <CreateRoomForm />
      </StoreContext.Provider>,
    );
    await userEvent.type(screen.getByLabelText(/nickname/i), 'Nick');
    await userEvent.click(screen.getByRole('button', { name: /create/i }));
    expect(api.createRoomAPI).toHaveBeenCalled();
    expect(store.getState().connection.roomCode).toBe('CODE');
    expect(store.getState().ui.currentView).toBe('game');
  });
});
