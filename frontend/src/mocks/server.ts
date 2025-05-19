import { setupServer } from "msw/node";
import { restHandlers } from "./handlers";
import { webSocketHandlers } from "./wsHandlers";

export const server = setupServer(...restHandlers, ...webSocketHandlers);
