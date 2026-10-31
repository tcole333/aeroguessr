import { act, render, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import { InnerApp } from './App';
import { StoreContext, createRootStore } from './store/createRootStore';

test('renders home page', () => {
  const store = createRootStore();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();
  const { getByText } = render(
    <StoreContext.Provider value={store}>
      <InnerApp />
    </StoreContext.Provider>,
  );
  expect(getByText(/aeroguessr/i)).toBeInTheDocument();
});

test('loads the client config on the home page, so the game map opens without waiting', async () => {
  const store = createRootStore();
  const { container, queryByRole } = render(
    <StoreContext.Provider value={store}>
      <InnerApp />
    </StoreContext.Provider>,
  );
  await waitFor(() => expect(store.getState().config.status).toBe('ready'));

  act(() => store.getState().ui.setCurrentView('game'));

  expect(queryByRole('status')).toBeNull();
  expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
});
