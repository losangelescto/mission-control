/**
 * Structured JSON logger for Next.js server runtime.
 *
 * In production we emit a single JSON object per line so Container Apps
 * log streams can be parsed by Log Analytics without a custom grok rule.
 * In development we keep the default Next.js pretty output.
 */

type LogLevel = "debug" | "info" | "warn" | "error";

type LogFields = Record<string, unknown>;

const ENV = process.env.NODE_ENV ?? "development";
const APP_ENV = process.env.APP_ENV ?? ENV;
const APP_VERSION = process.env.APP_VERSION ?? "dev";
const IS_PRODUCTION = ENV === "production";

function emit(level: LogLevel, message: string, fields: LogFields = {}): void {
  if (!IS_PRODUCTION) {
    const prefix = `[${level}]`;
    if (level === "error") {
      console.error(prefix, message, fields);
    } else if (level === "warn") {
      console.warn(prefix, message, fields);
    } else {
      console.log(prefix, message, fields);
    }
    return;
  }

  const payload = {
    timestamp: new Date().toISOString(),
    level: level.toUpperCase(),
    message,
    environment: APP_ENV,
    version: APP_VERSION,
    ...fields,
  };

  const stream = level === "error" || level === "warn" ? process.stderr : process.stdout;
  stream.write(JSON.stringify(payload) + "\n");
}

export const logger = {
  debug: (message: string, fields?: LogFields) => emit("debug", message, fields),
  info: (message: string, fields?: LogFields) => emit("info", message, fields),
  warn: (message: string, fields?: LogFields) => emit("warn", message, fields),
  error: (message: string, fields?: LogFields) => emit("error", message, fields),
};

export type RequestLogFields = {
  method: string;
  path: string;
  status?: number;
  duration_ms?: number;
  request_id?: string;
};

export function logRequest(fields: RequestLogFields): void {
  logger.info("request", fields);
}
