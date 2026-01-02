import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HomePage from '../HomePage';
import { StoreContext, createRootStore } from '../../store/createRootStore';

it('reveals forms when buttons clicked', async () => {
  const store = createRootStore();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();
  render(
    <StoreContext.Provider value={store}>
      <HomePage />
    </StoreContext.Provider>,
  );
  expect(screen.getByRole('button', { name: /create room/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /join room/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /start solo/i })).toBeInTheDocument();
  expect(screen.queryByLabelText(/round timeout/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/room code/i)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /create room/i }));
  expect(screen.getByLabelText(/round timeout/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /join room/i }));
  expect(screen.getByLabelText(/room code/i)).toBeInTheDocument();
});
