import { render } from '@testing-library/react';
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
  expect(getByText(/plane guessing game/i)).toBeInTheDocument();
});
