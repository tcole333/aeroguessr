import { http, HttpResponse } from "msw";

export const restHandlers = [
  http.get("/api/v0/healthz", () => {
    return HttpResponse.json({ status: "ok (mocked)" });
  }),
  http.post("/api/v0/rooms", async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ room_code: "ABCD", ws_url: `ws:///${body.host_nickname}` }, { status: 201 });
  }),
  http.post("/api/v0/rooms/:code/join", async ({ params, request }) => {
    const body = await request.json();
    return HttpResponse.json({ room_code: params.code, ws_url: `ws://${params.code}/${body.nickname}` });
  }),
];
