import { describe, it, expect } from "vitest";

describe("MSW Setup Verification", () => {
  it("should intercept a GET request to /api/v0/healthz and return mocked response", async () => {
    const response = await fetch("/api/v0/healthz");
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data).toEqual({ status: "ok (mocked)" });
  });

  it("placeholder for future WebSocket mock verification", () => {
    expect(true).toBe(true);
  });
});
