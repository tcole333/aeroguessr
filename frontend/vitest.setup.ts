/**
 * Vitest setup file for configuring the test environment
 */

import "@testing-library/jest-dom";
import { beforeAll, afterAll, afterEach } from "vitest";
import { setupServer } from "msw/node";

// Create MSW server for mocking API requests in tests
export const server = setupServer();

// Setup MSW server before tests
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

// Reset handlers after each test
afterEach(() => server.resetHandlers());

// Close server after all tests
afterAll(() => server.close());

// Mock console.error to fail tests on prop-type errors
const originalConsoleError = console.error;
console.error = (...args: any[]) => {
  // Fail tests if there's a prop-type error
  if (args[0]?.includes?.("Warning: Failed prop type")) {
    throw new Error(args[0]);
  }
  originalConsoleError(...args);
};
