import { render } from '@testing-library/react';
import { expect, test } from 'vitest';
import App from './App';

test('renders app shell', () => {
  const { container } = render(<App />);
  expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
});
