export const openapiSpec = {
  openapi: "3.0.3",
  info: {
    title: "Sui Transaction Service",
    version: "0.1.0",
    description: "Execute OneChain/Sui transactions for oracle updates & liquidation.",
  },
  servers: [{ url: "/" }],
  components: {
    securitySchemes: {
      ApiKeyAuth: {
        type: "apiKey",
        in: "header",
        name: "x-api-key",
      },
    },
    schemas: {
      UpdatePriceRequest: {
        type: "object",
        required: ["price"],
        properties: {
          price: { type: "number", example: 1100001 },
        },
      },
      LiquidateRequest: {
        type: "object",
        required: ["userAddress"],
        properties: {
          userAddress: {
            type: "string",
            example: "0x" + "0".repeat(64),
          },
        },
      },
    },
  },
  paths: {
    "/health": {
      get: {
        summary: "Health check",
        responses: { "200": { description: "OK" } },
      },
    },
    "/api/signer": {
      get: {
        summary: "Get signer info",
        security: [{ ApiKeyAuth: [] }],
        responses: { "200": { description: "OK" }, "401": { description: "Unauthorized" } },
      },
    },
    "/api/update-price": {
      post: {
        summary: "Update oracle price",
        security: [{ ApiKeyAuth: [] }],
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/UpdatePriceRequest" } } },
        },
        responses: {
          "200": { description: "Success" },
          "400": { description: "Bad request" },
          "401": { description: "Unauthorized" },
          "500": { description: "Server error" },
        },
      },
    },
    "/api/liquidate": {
      post: {
        summary: "Liquidate position",
        security: [{ ApiKeyAuth: [] }],
        requestBody: {
          required: true,
          content: { "application/json": { schema: { $ref: "#/components/schemas/LiquidateRequest" } } },
        },
        responses: {
          "200": { description: "Success" },
          "400": { description: "Bad request" },
          "401": { description: "Unauthorized" },
          "500": { description: "Server error" },
        },
      },
    },
  },
} as const;
