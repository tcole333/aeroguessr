import { expect, test } from 'vitest';
import App from './App';
import { render, screen } from '@testing-library/react';

test('renders learn react link', () => {
  render(<App />);
  // Example assertion, update if your App.tsx is different
  const linkElement = screen.getByText(/Plane Guessing Game/i);
  expect(linkElement).toBeDefined();
});
