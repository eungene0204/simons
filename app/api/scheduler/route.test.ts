import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { runSchedulerAction } from "@/lib/server/scheduler-actions";

vi.mock("@/lib/server/scheduler-actions", () => ({
  runSchedulerAction: vi.fn(),
}));

const mockRunSchedulerAction = vi.mocked(runSchedulerAction);

function makeRequest(headers: Record<string, string> = {}): Request {
  return new Request("http://localhost/api/scheduler", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({ action: "market-close" }),
  });
}

async function loadPost() {
  vi.resetModules();
  return (await import("./route")).POST;
}

describe("/api/scheduler 인증", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRunSchedulerAction.mockResolvedValue({ ok: true } as any);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  // 이 라우트는 전 사용자의 자동매매 계좌를 일괄 시작·정지한다.
  it("운영에서 시크릿이 없으면 아무도 부를 수 없다(fail closed)", async () => {
    vi.stubEnv("SCHEDULER_SECRET", "");
    vi.stubEnv("NODE_ENV", "production");
    const POST = await loadPost();

    const response = await POST(makeRequest());

    expect(response.status).toBe(401);
    expect(mockRunSchedulerAction).not.toHaveBeenCalled();
  });

  it("시크릿이 설정돼 있으면 Bearer 토큰이 맞아야 통과한다", async () => {
    vi.stubEnv("SCHEDULER_SECRET", "s3cret");
    vi.stubEnv("NODE_ENV", "production");
    const POST = await loadPost();

    const denied = await POST(makeRequest({ Authorization: "Bearer wrong" }));
    expect(denied.status).toBe(401);

    const allowed = await POST(makeRequest({ Authorization: "Bearer s3cret" }));
    expect(allowed.status).toBe(200);
    expect(mockRunSchedulerAction).toHaveBeenCalledTimes(1);
  });

  it("개발 환경에서는 시크릿 없이도 부를 수 있다", async () => {
    vi.stubEnv("SCHEDULER_SECRET", "");
    vi.stubEnv("NODE_ENV", "development");
    const POST = await loadPost();

    const response = await POST(makeRequest());

    expect(response.status).toBe(200);
  });
});
