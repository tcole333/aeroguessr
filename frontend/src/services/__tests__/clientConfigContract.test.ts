import { describe, expect, it } from 'vitest';
import type { ZodRawShape } from 'zod';
import { openapi } from '../../../types/api';
import { ClientConfigSchema } from '../apiService';

// The zod schema is written by hand; types/api.ts is generated from the backend, and CI fails
// when it drifts from the code. Comparing the two catches a backend change to GET
// /api/v0/config that would otherwise pass every test and break the map in every browser.

interface PropertySchema {
  anyOf?: readonly { type?: string }[];
}

interface ObjectSchema {
  properties: Record<string, PropertySchema>;
  required?: readonly string[];
}

const apiSchemas = openapi.components.schemas as unknown as Record<string, ObjectSchema>;

const zodShapes: [string, ZodRawShape][] = [
  ['ClientConfig', ClientConfigSchema.shape],
  ['MonitoredAirport', ClientConfigSchema.shape.monitored_airport.shape],
  ['LatLon', ClientConfigSchema.shape.center.shape],
];

describe.each(zodShapes)('ClientConfigSchema against the API contract: %s', (name, shape) => {
  const apiSchema = apiSchemas[name];

  it('has the same fields', () => {
    expect(Object.keys(shape).sort()).toEqual(Object.keys(apiSchema.properties).sort());
  });

  it('requires the same fields', () => {
    const required = Object.keys(shape).filter((field) => !shape[field].isOptional());
    expect(required.sort()).toEqual([...(apiSchema.required ?? [])].sort());
  });

  it('allows null in the same fields', () => {
    const nullable = Object.keys(shape).filter((field) => shape[field].safeParse(null).success);
    const apiNullable = Object.entries(apiSchema.properties)
      .filter(([, property]) => property.anyOf?.some((option) => option.type === 'null'))
      .map(([field]) => field);
    expect(nullable.sort()).toEqual(apiNullable.sort());
  });
});
