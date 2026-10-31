/**
 * Vitest setup file for configuring the test environment
 */

import "@testing-library/jest-dom";
import { beforeAll, afterAll, afterEach } from "vitest";
import { server } from "./src/mocks/server";

// jsdom does no layout, so it leaves out scrollIntoView, which AirportAutocomplete calls
// when an option becomes active
Element.prototype.scrollIntoView = () => {};

// Setup MSW server before tests
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  server.resetHandlers();
  // The store persists the session here, so a test's room would reach the next test's store
  localStorage.clear();
});

// Close server after all tests
afterAll(() => server.close());
