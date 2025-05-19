import { http, HttpResponse } from "msw";

export const restHandlers = [
  http.get("/api/v0/healthz", () => {
    return HttpResponse.json({ status: "ok (mocked)" });
  }),
];
