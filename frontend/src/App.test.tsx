import { render } from '@testing-library/react';
import { expect, test } from 'vitest';
import App from './App';

test('renders home page', () => {
  const { getByText } = render(<App />);
  expect(getByText(/plane guessing game/i)).toBeInTheDocument();
});
