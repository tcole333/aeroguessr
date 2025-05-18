import { promises as fs } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import yaml from 'js-yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = join(__dirname, '..', '..');
const docsDir = join(rootDir, 'docs');
const typesDir = join(rootDir, 'frontend/types');

function header(src) {
  return `/**\n * AUTO-GENERATED FILE. DO NOT EDIT.\n * Source: ${src}\n * Generated: ${new Date().toISOString()}\n */\n`;
}

function genPingPong(_def) {
  return `export const PingPongPayloadSchema = z.object({ seq: z.number().int() });\nexport type PingPongPayload = z.infer<typeof PingPongPayloadSchema>;\n\nexport const PingSchema = z.object({ type: z.literal('ping'), payload: PingPongPayloadSchema, ts: z.number().optional() });\nexport type Ping = z.infer<typeof PingSchema>;\n\nexport const PongSchema = z.object({ type: z.literal('pong'), payload: PingPongPayloadSchema, ts: z.number().optional() });\nexport type Pong = z.infer<typeof PongSchema>;\n`;
}

async function generateWs() {
  const wsPath = join(docsDir, 'ws_schema.yaml');
  const wsYaml = await fs.readFile(wsPath, 'utf8');
  const ws = yaml.load(wsYaml);
  const parts = [header('docs/ws_schema.yaml'), "import { z } from 'zod';\n"];
  if (ws.$defs && ws.$defs.PingPongPayload) {
    parts.push(genPingPong(ws.$defs.PingPongPayload));
  }
  parts.push(
    'export const InboundMessageSchema = z.discriminatedUnion("type", [PongSchema]);',
    'export type InboundMessage = z.infer<typeof InboundMessageSchema>;',
    'export const OutboundMessageSchema = z.discriminatedUnion("type", [PingSchema]);',
    'export type OutboundMessage = z.infer<typeof OutboundMessageSchema>;',
  );
  await fs.writeFile(join(typesDir, 'ws.ts'), parts.join('\n'));
}

async function generateApi() {
  const apiPath = join(docsDir, 'api_openapi.yaml');
  const apiYaml = await fs.readFile(apiPath, 'utf8');
  const obj = yaml.load(apiYaml);
  const out =
    header('docs/api_openapi.yaml') +
    `export const openapi = ${JSON.stringify(obj, null, 2)} as const;\n`;
  await fs.writeFile(join(typesDir, 'api.ts'), out);
}

async function main() {
  await fs.mkdir(typesDir, { recursive: true });
  await generateApi();
  await generateWs();
  console.log('Generated API and WS types');
}

main().catch((err) => {
  console.error('Error generating schema types', err);
  process.exit(1);
});
