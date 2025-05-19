import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPanelContent from '../SettingsPanelContent';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';

function setup({ darkMode = false, host = null, isSolo = false } = {}) {
  const store = createRootStore();
  if (darkMode) {
    store.getState().ui.toggleDarkMode();
  }
  store.getState().game.hostNickname = host;
  store.getState().game.isSolo = isSolo;
  (store.getState().connection as unknown as { nickname?: string }).nickname = 'Me';
  return { store, ...render(
    <StoreContext.Provider value={store}>
      <SettingsPanelContent />
    </StoreContext.Provider>,
  )};
}

describe('SettingsPanelContent', () => {
  it('toggles night mode', async () => {
    const { store } = setup();
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();
    await userEvent.click(checkbox);
    expect(store.getState().ui.darkMode).toBe(true);
  });

  it('fires leave room action', async () => {
    setup();
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    await userEvent.click(screen.getByRole('button', { name: /leave room/i }));
    expect(logSpy).toHaveBeenCalled();
    logSpy.mockRestore();
  });

  it('shows host controls when host', () => {
    setup({ host: 'Me', isSolo: false });
    expect(screen.getByText(/host controls/i)).toBeInTheDocument();
  });
});
