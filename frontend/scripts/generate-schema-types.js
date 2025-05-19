import { promises as fs } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import yaml from "js-yaml";

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = join(__dirname, "..", "..");
const docsDir = join(rootDir, "docs");
const typesDir = join(rootDir, "frontend/types");

function header(src) {
  return `/**\n * AUTO-GENERATED FILE. DO NOT EDIT.\n * Source: ${src}\n * Generated: ${new Date().toISOString()}\n */\n`;
}

function schemaToZod(schema, defs) {
  if (!schema) {
    return "z.any()";
  }
  if (schema.$ref) {
    return defs[schema.$ref] || "z.any()";
  }
  if (schema.anyOf) {
    const parts = schema.anyOf.map((s) => schemaToZod(s, defs));
    return `z.union([${parts.join(", ")}])`;
  }
  switch (schema.type) {
    case "string":
      if (schema.enum) {
        return `z.enum([${schema.enum.map((e) => `'${e}'`).join(", ")}])`;
      }
      return "z.string()";
    case "integer":
      return "z.number().int()";
    case "number":
      return "z.number()";
    case "boolean":
      return "z.boolean()";
    case "array":
      return `z.array(${schema.items ? schemaToZod(schema.items, defs) : "z.any()"})`;
    case "object": {
      const props = schema.properties || {};
      const required = schema.required || [];
      const propStr = Object.entries(props)
        .map(([k, v]) => {
          let str = schemaToZod(v, defs);
          if (!required.includes(k)) str += ".optional()";
          return `${JSON.stringify(k)}: ${str}`;
        })
        .join(", ");
      if (schema.additionalProperties) {
        const ap =
          schema.additionalProperties === true
            ? "z.any()"
            : schemaToZod(schema.additionalProperties, defs);
        return `z.record(${ap})`;
      }
      return `z.object({ ${propStr} })`;
    }
    default:
      return "z.any()";
  }
}

async function generateWs() {
  const wsPath = join(docsDir, "ws_schema.yaml");
  const wsYaml = await fs.readFile(wsPath, "utf8");
  const ws = yaml.load(wsYaml);

  const parts = [header("docs/ws_schema.yaml"), "import { z } from 'zod';\n"];
  const refMap = {};

  function processDefs(defs) {
    Object.entries(defs || {}).forEach(([name, def]) => {
      if (def.$defs) processDefs(def.$defs);
      const schemaStr = schemaToZod(def, refMap);
      parts.push(`export const ${name}Schema = ${schemaStr};`);
      parts.push(`export type ${name} = z.infer<typeof ${name}Schema>;`);
      refMap[`#/$defs/${name}`] = `${name}Schema`;
    });
  }

  processDefs(ws.$defs);

  const inbound = new Set([
    "stateSync",
    "delta",
    "roundStart",
    "roundResult",
    "playerJoined",
    "playerLeft",
    "newHost",
    "error",
    "pong",
    "planeSelectedConfirm",
  ]);

  const inboundSchemas = [];
  const outboundSchemas = [];

  Object.entries(ws.messages).forEach(([msgType, msgDef]) => {
    const payloadSchema = schemaToZod(msgDef.payload, refMap);
    const name = `${msgType[0].toUpperCase()}${msgType.slice(1)}Schema`;
    parts.push(
      `export const ${name} = z.object({ type: z.literal('${msgType}'), payload: ${payloadSchema}.optional(), ts: z.number().optional() });`,
    );
    const typeName = `${msgType[0].toUpperCase()}${msgType.slice(1)}`;
    parts.push(`export type ${typeName} = z.infer<typeof ${name}>;`);
    (inbound.has(msgType) ? inboundSchemas : outboundSchemas).push(name);
  });

  parts.push(
    `export const InboundMessageSchema = z.discriminatedUnion('type', [${inboundSchemas.join(", ")}]);`,
    `export type InboundMessage = z.infer<typeof InboundMessageSchema>;`,
    `export const OutboundMessageSchema = z.discriminatedUnion('type', [${outboundSchemas.join(", ")}]);`,
    `export type OutboundMessage = z.infer<typeof OutboundMessageSchema>;`,
  );

  await fs.writeFile(join(typesDir, "ws.ts"), parts.join("\n"));
}

async function generateApi() {
  const apiPath = join(docsDir, "api_openapi.yaml");
  const apiYaml = await fs.readFile(apiPath, "utf8");
  const obj = yaml.load(apiYaml);
  const out =
    header("docs/api_openapi.yaml") +
    `export const openapi = ${JSON.stringify(obj, null, 2)} as const;\n`;
  await fs.writeFile(join(typesDir, "api.ts"), out);
}

async function main() {
  await fs.mkdir(typesDir, { recursive: true });
  await generateApi();
  await generateWs();
  console.log("Generated API and WS types");
}

main().catch((err) => {
  console.error("Error generating schema types", err);
  process.exit(1);
});
