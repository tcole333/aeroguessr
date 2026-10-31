import { http, HttpResponse } from "msw";
import { seattleClientConfig } from "./clientConfig";

export const restHandlers = [
  http.get("/api/v0/config", () => HttpResponse.json(seattleClientConfig)),
];
