import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

// 비로그인 폴백 없음 — 2026-09-03 감사 전에는 userId=1로 대체해, 1번 계정이 PREMIUM이면 누구나
// 리서치를 실행할 수 있었다. 백엔드는 X-User-Id의 planTier를 DB에서 다시 확인한다.
// 세션은 getCurrentUser로 인정한다 — 토큰만 보면 정지·이용 기한이 지난 계정도 통과한다(2026-09-17).
async function resolveUserId(): Promise<number | null> {
  const user = await getCurrentUser();
  return user?.id ?? null;
}

async function proxyToBackend(
  req: NextRequest,
  pathSegments: string[],
  method: string,
  bodyText?: string
): Promise<Response> {
  const userId = await resolveUserId();
  if (userId == null) {
    return NextResponse.json({ error: "로그인이 필요합니다." }, { status: 401 });
  }

  const pathStr = pathSegments.join("/");
  const target = `${BACKEND}/research/${pathStr}${req.nextUrl.search}`;

  try {
    const res = await fetch(target, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": String(userId),
      },
      body: bodyText || undefined,
      cache: "no-store",
    });

    const contentType = res.headers.get("content-type") ?? "";

    if (contentType.includes("text/event-stream")) {
      return new Response(res.body, {
        status: res.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
          "Connection": "keep-alive",
          "X-Accel-Buffering": "no",
        },
      });
    }

    const text = await res.text();
    return new Response(text, {
      status: res.status,
      headers: { "Content-Type": contentType || "application/json" },
    });
  } catch (err: any) {
    return NextResponse.json(
      { error: `백엔드 연결 실패: ${err.message}` },
      { status: 502 }
    );
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxyToBackend(req, path, "GET");
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  const body = await req.text();
  return proxyToBackend(req, path, "POST", body);
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxyToBackend(req, path, "DELETE");
}
