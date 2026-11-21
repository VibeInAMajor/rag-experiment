export type ApiErrorKind =
  "transport" | "timeout" | "cancelled" | "protocol" | "http" | "configuration";

export class WorkbenchApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly code: string;
  readonly httpStatus?: number;
  readonly retryable: boolean;
  readonly traceId?: string;
  readonly requestId?: string;
  readonly runId?: string;

  constructor(
    message: string,
    details: {
      kind: ApiErrorKind;
      code: string;
      httpStatus?: number;
      retryable?: boolean;
      traceId?: string;
      requestId?: string;
      runId?: string;
    },
  ) {
    super(message);
    this.name = "WorkbenchApiError";
    this.kind = details.kind;
    this.code = details.code;
    this.httpStatus = details.httpStatus;
    this.retryable = details.retryable ?? false;
    this.traceId = details.traceId;
    this.requestId = details.requestId;
    this.runId = details.runId;
  }
}

export function invalidResponse(): never {
  throw new WorkbenchApiError(
    "Backend response is incompatible. Refresh after checking service versions.",
    {
      kind: "protocol",
      code: "INVALID_RESPONSE",
    },
  );
}
