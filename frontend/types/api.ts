/**
 * AUTO-GENERATED FILE. DO NOT EDIT.
 * Source: docs/api_openapi.yaml
 */
export const openapi = {
  "openapi": "3.1.0",
  "info": {
    "title": "AeroGuessr API",
    "description": "API for managing game rooms, players, and flight data.",
    "version": "0.1.0"
  },
  "paths": {
    "/": {
      "get": {
        "summary": "Read Root",
        "description": "Root endpoint providing a basic welcome message.",
        "operationId": "read_root__get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "additionalProperties": {
                    "type": "string"
                  },
                  "type": "object",
                  "title": "Response Read Root  Get"
                }
              }
            }
          }
        }
      }
    },
    "/healthz": {
      "get": {
        "tags": [
          "health"
        ],
        "summary": "Liveness",
        "description": "Liveness probe: the API process is up and serving requests. Names the version too.\n\nDoes no I/O on purpose, so it fails only when this process is broken. The\nDocker healthcheck uses it; dependency checks belong to /readyz. The version\nis worked out at startup.",
        "operationId": "liveness_healthz_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/LivenessResponse"
                }
              }
            }
          }
        }
      }
    },
    "/readyz": {
      "get": {
        "tags": [
          "health"
        ],
        "summary": "Readiness",
        "description": "Readiness probe: Redis is up and ingest is heartbeating on its ADS-B feed.\n\nReturns 503 when not ready. The deploy gate (scripts/auto-update.sh) uses this.\nAn empty sky is ready: plane counts are not part of the check.",
        "operationId": "readiness_readyz_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ReadinessResponse"
                }
              }
            }
          },
          "503": {
            "description": "Not ready; `checks` and `reason` say why",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ReadinessResponse"
                }
              }
            }
          }
        }
      }
    },
    "/api/v0/config": {
      "get": {
        "tags": [
          "config"
        ],
        "summary": "Read Client Config",
        "description": "The receiver's location, the monitored airport, the antenna range and the basemap.\n\nThe frontend reads it once at startup, so one frontend build works at any location.\nStatic and public: it holds no secrets and names no route's airports.",
        "operationId": "read_client_config_api_v0_config_get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ClientConfig"
                }
              }
            }
          }
        }
      }
    },
    "/api/v0/rooms": {
      "post": {
        "tags": [
          "rooms"
        ],
        "summary": "Create a new game room",
        "description": "Creates a new game room with a unique code and returns the code and WebSocket URL for the host.",
        "operationId": "create_room_api_v0_rooms_post",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/RoomCreateRequest"
              }
            }
          },
          "required": true
        },
        "responses": {
          "201": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/RoomCreateResponse"
                }
              }
            }
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    },
    "/api/v0/rooms/{room_code}/join": {
      "post": {
        "tags": [
          "rooms"
        ],
        "summary": "Join an existing game room",
        "description": "Allows a player to join a room using a code and nickname. Checks for room existence and nickname uniqueness.",
        "operationId": "join_room_api_v0_rooms__room_code__join_post",
        "parameters": [
          {
            "name": "room_code",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string",
              "title": "Room Code"
            }
          }
        ],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/RoomJoinRequest"
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/RoomJoinResponse"
                }
              }
            }
          },
          "404": {
            "description": "Room not found"
          },
          "409": {
            "description": "Nickname already taken in this room"
          },
          "422": {
            "description": "Validation Error",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/HTTPValidationError"
                }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "ClientConfig": {
        "properties": {
          "center": {
            "$ref": "#/components/schemas/LatLon",
            "description": "Where the map opens: the receiver's location (CENTER_LAT, CENTER_LON) rounded to 2 decimals, about 1 km, so the exact position stays private."
          },
          "monitored_airport": {
            "$ref": "#/components/schemas/MonitoredAirport"
          },
          "max_antenna_range_km": {
            "type": "number",
            "title": "Max Antenna Range Km",
            "description": "Planes farther than this from the centre leave the map."
          },
          "map_style_url": {
            "type": "string",
            "title": "Map Style Url",
            "description": "MapLibre style URL for the basemap."
          },
          "attributions": {
            "items": {
              "type": "string"
            },
            "type": "array",
            "minItems": 1,
            "title": "Attributions",
            "description": "Credits the map must show, one per data source, as HTML (the format TileJSON and Leaflet use for attributions)."
          },
          "version": {
            "type": "string",
            "title": "Version",
            "description": "The version this install runs, for bug reports: a release image's tag, or pyproject.toml's version plus the git commit, e.g. 0.1.0-alpha.1+1a2b3c4."
          }
        },
        "type": "object",
        "required": [
          "center",
          "monitored_airport",
          "max_antenna_range_km",
          "map_style_url",
          "attributions",
          "version"
        ],
        "title": "ClientConfig",
        "description": "Static settings the browser reads once at startup."
      },
      "HTTPValidationError": {
        "properties": {
          "detail": {
            "items": {
              "$ref": "#/components/schemas/ValidationError"
            },
            "type": "array",
            "title": "Detail"
          }
        },
        "type": "object",
        "title": "HTTPValidationError"
      },
      "LatLon": {
        "properties": {
          "lat": {
            "type": "number",
            "maximum": 90,
            "minimum": -90,
            "title": "Lat",
            "description": "Latitude in decimal degrees."
          },
          "lon": {
            "type": "number",
            "maximum": 180,
            "minimum": -180,
            "title": "Lon",
            "description": "Longitude in decimal degrees."
          }
        },
        "type": "object",
        "required": [
          "lat",
          "lon"
        ],
        "title": "LatLon",
        "description": "A position in decimal degrees."
      },
      "LivenessResponse": {
        "properties": {
          "status": {
            "type": "string",
            "const": "ok",
            "title": "Status",
            "default": "ok"
          },
          "version": {
            "type": "string",
            "title": "Version",
            "description": "The version this install runs, as in GET /api/v0/config."
          }
        },
        "type": "object",
        "required": [
          "version"
        ],
        "title": "LivenessResponse",
        "description": "The API process is up and serving requests."
      },
      "MonitoredAirport": {
        "properties": {
          "icao": {
            "type": "string",
            "title": "Icao",
            "description": "ICAO code, e.g. KSEA."
          },
          "iata": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Iata",
            "description": "IATA code, e.g. SEA; null when there is none."
          },
          "name": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Name",
            "description": "Airport name, e.g. Seattle–Tacoma International."
          },
          "position": {
            "anyOf": [
              {
                "$ref": "#/components/schemas/LatLon"
              },
              {
                "type": "null"
              }
            ],
            "description": "Where the airport is."
          }
        },
        "type": "object",
        "required": [
          "icao",
          "iata",
          "name",
          "position"
        ],
        "title": "MonitoredAirport",
        "description": "The airport every round is about (MONITORED_AIRPORT_ICAO).\n\nThe airport dataset supplies the other fields. They are null when the airport is not in\nthe dataset, which still works for play: answers must be in the dataset, the monitored\nairport need not be."
      },
      "ReadinessChecks": {
        "properties": {
          "redis": {
            "type": "string",
            "enum": [
              "ok",
              "down"
            ],
            "title": "Redis",
            "description": "Whether Redis answered within the time limit."
          },
          "ingest": {
            "type": "string",
            "enum": [
              "ok",
              "down",
              "stale",
              "feed_disconnected",
              "unknown"
            ],
            "title": "Ingest",
            "description": "ok: fresh heartbeat with the ADS-B feed connected. down: no usable heartbeat from the current ingest run. stale: heartbeat older than the threshold. feed_disconnected: ingest is alive but not connected to its feed. unknown: Redis is down, so ingest could not be checked."
          }
        },
        "type": "object",
        "required": [
          "redis",
          "ingest"
        ],
        "title": "ReadinessChecks"
      },
      "ReadinessResponse": {
        "properties": {
          "status": {
            "type": "string",
            "enum": [
              "ready",
              "not_ready"
            ],
            "title": "Status"
          },
          "checks": {
            "$ref": "#/components/schemas/ReadinessChecks"
          },
          "reason": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ],
            "title": "Reason",
            "description": "Why the service is not ready; null when ready."
          },
          "ingest_heartbeat_age_seconds": {
            "anyOf": [
              {
                "type": "number"
              },
              {
                "type": "null"
              }
            ],
            "title": "Ingest Heartbeat Age Seconds",
            "description": "Age of the latest ingest heartbeat, when there is one."
          }
        },
        "type": "object",
        "required": [
          "status",
          "checks"
        ],
        "title": "ReadinessResponse",
        "description": "Whether the service can run games: Redis is up and ingest is on its feed."
      },
      "RoomCreateRequest": {
        "properties": {
          "host_nickname": {
            "type": "string",
            "maxLength": 30,
            "minLength": 3,
            "title": "Host Nickname",
            "description": "Nickname for the player hosting the room."
          },
          "mode": {
            "$ref": "#/components/schemas/ScoringMode",
            "description": "Scoring mode for the room.",
            "default": "Exact"
          },
          "round_timeout_seconds": {
            "type": "integer",
            "maximum": 120,
            "minimum": 10,
            "title": "Round Timeout Seconds",
            "description": "Duration of each guessing round in seconds.",
            "default": 30
          }
        },
        "type": "object",
        "required": [
          "host_nickname"
        ],
        "title": "RoomCreateRequest",
        "description": "Request body for creating a new game room.",
        "example": {
          "host_nickname": "HostessHannah",
          "mode": "Distance",
          "round_timeout_seconds": 60
        }
      },
      "RoomCreateResponse": {
        "properties": {
          "room_code": {
            "type": "string",
            "title": "Room Code",
            "description": "The unique 4-letter code for the created room."
          },
          "ws_url": {
            "type": "string",
            "title": "Ws Url",
            "description": "The WebSocket URL for the host to connect to."
          }
        },
        "type": "object",
        "required": [
          "room_code",
          "ws_url"
        ],
        "title": "RoomCreateResponse",
        "description": "Response body after successfully creating a game room.",
        "example": {
          "room_code": "ABCD",
          "ws_url": "ws://localhost:8000/api/v0/rooms/ws/ABCD/HostessHannah"
        }
      },
      "RoomJoinRequest": {
        "properties": {
          "nickname": {
            "type": "string",
            "maxLength": 30,
            "minLength": 3,
            "title": "Nickname",
            "description": "Nickname for the player joining the room."
          }
        },
        "type": "object",
        "required": [
          "nickname"
        ],
        "title": "RoomJoinRequest",
        "description": "Request body for joining an existing game room.",
        "example": {
          "nickname": "JoinerJane"
        }
      },
      "RoomJoinResponse": {
        "properties": {
          "room_code": {
            "type": "string",
            "title": "Room Code",
            "description": "Room code assigned for the joined session."
          },
          "ws_url": {
            "type": "string",
            "title": "Ws Url",
            "description": "The WebSocket URL for the player to connect to."
          }
        },
        "type": "object",
        "required": [
          "room_code",
          "ws_url"
        ],
        "title": "RoomJoinResponse",
        "description": "Response body after successfully joining a game room.",
        "example": {
          "room_code": "ABCD",
          "ws_url": "ws://localhost:8000/api/v0/rooms/ws/ABCD/JoinerJane"
        }
      },
      "ScoringMode": {
        "type": "string",
        "enum": [
          "Exact",
          "Distance"
        ],
        "title": "ScoringMode",
        "description": "Enum for available scoring modes."
      },
      "ValidationError": {
        "properties": {
          "loc": {
            "items": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "integer"
                }
              ]
            },
            "type": "array",
            "title": "Location"
          },
          "msg": {
            "type": "string",
            "title": "Message"
          },
          "type": {
            "type": "string",
            "title": "Error Type"
          }
        },
        "type": "object",
        "required": [
          "loc",
          "msg",
          "type"
        ],
        "title": "ValidationError"
      }
    }
  }
} as const;
