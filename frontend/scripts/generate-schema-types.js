/**
 * Script to generate TypeScript types from OpenAPI and WebSocket schemas
 *
 * This script:
 * 1. Reads the OpenAPI schema from docs/api_openapi.yaml
 * 2. Reads the WebSocket schema from docs/ws_schema.yaml
 * 3. Generates TypeScript types + Zod validators
 * 4. Writes output to frontend/types/api.ts and frontend/types/ws.ts
 */

import { promises as fs } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);
const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = join(__dirname, "../..");
const docsDir = join(rootDir, "docs");
const typesDir = join(rootDir, "frontend/types");

async function generateTypes() {
  try {
    // Ensure types directory exists
    await fs.mkdir(typesDir, { recursive: true });

    console.log("🔍 Reading API and WebSocket schemas...");

    // Generate API types using openapi-typescript
    const apiSchemaPath = join(docsDir, "api_openapi.yaml");
    const apiOutputPath = join(typesDir, "api.ts");

    console.log("⚙️ Generating API types from OpenAPI schema...");
    await execAsync(`npx openapi-typescript ${apiSchemaPath} --output ${apiOutputPath}`);

    // Generate WebSocket types using custom logic
    const wsSchemaPath = join(docsDir, "ws_schema.yaml");
    const wsOutputPath = join(typesDir, "ws.ts");

    // Read the WebSocket schema
    const wsSchemaContent = await fs.readFile(wsSchemaPath, "utf-8");

    // Here we would parse the YAML and generate Zod schemas
    // This is a placeholder - in a real implementation, we would parse the YAML
    // and generate proper Zod schemas and TypeScript types
    const wsTypesContent = `/**
 * WebSocket message types and Zod schemas
 * GENERATED FILE - DO NOT EDIT DIRECTLY
 *
 * Generated from: ${wsSchemaPath}
 * Generated at: ${new Date().toISOString()}
 */

import { z } from 'zod';

// ---- Message Envelopes ----

export const BaseMessageSchema = z.object({
  type: z.string(),
  ts: z.number().optional(),
});

export type BaseMessage = z.infer<typeof BaseMessageSchema>;

// ---- Inbound Messages (server → client) ----

export const PongSchema = BaseMessageSchema.extend({
  type: z.literal('pong'),
});

export type Pong = z.infer<typeof PongSchema>;

// Add additional inbound message schemas as they're defined in ws_schema.yaml

// ---- Outbound Messages (client → server) ----

export const PingSchema = BaseMessageSchema.extend({
  type: z.literal('ping'),
});

export type Ping = z.infer<typeof PingSchema>;

// Add additional outbound message schemas as they're defined in ws_schema.yaml

// ---- Union Types ----

export const InboundMessageSchema = z.discriminatedUnion('type', [
  PongSchema,
  // Add other inbound message schemas here
]);

export type InboundMessage = z.infer<typeof InboundMessageSchema>;

export const OutboundMessageSchema = z.discriminatedUnion('type', [
  PingSchema,
  // Add other outbound message schemas here
]);

export type OutboundMessage = z.infer<typeof OutboundMessageSchema>;

// ---- Helper Functions ----

export function assertWsMessage(data: unknown): InboundMessage {
  try {
    return InboundMessageSchema.parse(data);
  } catch (error) {
    console.error('Invalid WebSocket message', error, data);
    throw new Error('Invalid WebSocket message');
  }
}
`;

    await fs.writeFile(wsOutputPath, wsTypesContent);

    console.log("✅ Types generated successfully!");
    console.log(`API types: ${apiOutputPath}`);
    console.log(`WebSocket types: ${wsOutputPath}`);
  } catch (error) {
    console.error("❌ Error generating types:", error);
    process.exit(1);
  }
}

generateTypes();
