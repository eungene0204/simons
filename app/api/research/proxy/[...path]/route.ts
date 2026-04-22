import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifyToken } from "@/lib/auth";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

const DEV_USER_ID = 1; // 테스트용 고정 userId (로그인 불필요)

async function resolveUserId(): Promise<number> {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("token")?.value;
    if (token) {
      const decoded = verifyToken(token);
      if (decoded?.userId) return decoded.userId;
    }
  } catch {}
  return DEV_USER_ID;
}

async function proxyToBackend(
  req: NextRequest,
  pathSegments: string[],
  method: string,
  bodyText?: string
): Promise<Response> {
  const userId = await resolveUserId();

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
