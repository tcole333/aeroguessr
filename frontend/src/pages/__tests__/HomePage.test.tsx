import { render, screen } from '@testing-library/react';
import HomePage from '../HomePage';
import { StoreContext, createRootStore } from '../../store/createRootStore';

it('renders all forms', () => {
  const store = createRootStore();
  render(
    <StoreContext.Provider value={store}>
      <HomePage />
    </StoreContext.Provider>,
  );
  expect(screen.getByText(/create room/i)).toBeInTheDocument();
  expect(screen.getByText(/join room/i)).toBeInTheDocument();
  expect(screen.getByText(/start solo/i)).toBeInTheDocument();
});
