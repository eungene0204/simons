import { noStoreJson, PUBLIC_ID_PATTERN } from "../../response";
import { BoardError } from "@/lib/board/rules";
import { identity } from "@/lib/board/server";
import { NotPublicError } from "@/lib/server/publicSimulation/access";
import {
  BaselineChangedError, InvalidParameterError, RateLimitedError, SimulationFailedError, runModified,
  type Override,
} from "@/lib/server/publicSimulation/modified";

export const dynamic = "force-dynamic";

const MAX_OVERRIDES = 20;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function parseBody(body: any): { overrides: Override[]; baseSnapshotHash: string; dataAsOf: string } | null {
  if (!body || typeof body !== "object" || !Array.isArray(body.overrides) || body.overrides.length > MAX_OVERRIDES) return null;
  const overrides: Override[] = [];
  for (const item of body.overrides) {
    if (!item || typeof item.path !== "string" || item.path.length > 120 || typeof item.value !== "number" || !Number.isFinite(item.value)) {
      return null;
    }
    overrides.push({ path: item.path, value: item.value });
  }
  const { baseSnapshotHash, dataAsOf } = body;
  if (typeof baseSnapshotHash !== "string" || !/^[0-9a-f]{64}$/.test(baseSnapshotHash)) return null;
  if (typeof dataAsOf !== "string" || !DATE_PATTERN.test(dataAsOf)) return null;
  return { overrides, baseSnapshotHash, dataAsOf };
}

// 방문자 수정 시뮬레이션 — 로그인 불필요, 사용자 기록·한도에 쓰지 않는다. 서버 호출마다 예시 등록부를 다시 확인한다.
export async function POST(request: Request, { params }: { params: { publicId: string } }) {
  if (!PUBLIC_ID_PATTERN.test(params.publicId)) return noStoreJson({ code: "NOT_FOUND" }, 404);
  const body = parseBody(await request.json().catch(() => null));
  if (!body) return noStoreJson({ code: "INVALID_REQUEST" }, 400);

  try {
    const result = await runModified({ publicId: params.publicId, identity: identity(request), ...body });
    return noStoreJson(result);
  } catch (error) {
    if (error instanceof NotPublicError) return noStoreJson({ code: "STRATEGY_NOT_PUBLIC" }, 404);
    if (error instanceof BaselineChangedError) return noStoreJson({ code: "BASELINE_CHANGED", reason: error.reason }, 409);
    if (error instanceof InvalidParameterError) return noStoreJson({ code: "INVALID_PARAMETER", errors: error.errors }, 400);
    if (error instanceof RateLimitedError) {
      return noStoreJson({ code: "RATE_LIMITED", retryAfterSeconds: error.retryAfterSeconds }, 429, {
        "Retry-After": String(error.retryAfterSeconds),
      });
    }
    if (error instanceof SimulationFailedError) {
      return noStoreJson({ code: error.code, retryAfterSeconds: error.retryAfterSeconds }, error.status);
    }
    if (error instanceof BoardError) return noStoreJson({ code: "RATE_LIMIT_UNAVAILABLE" }, error.status);
    console.error("[strategy-simulation] run failed", error);
    return noStoreJson({ code: "ENGINE_ERROR" }, 500);
  }
}
