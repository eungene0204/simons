import { NextRequest, NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import {
  MAX_CHAT_LOG_SESSION_ID_CHARS,
  MAX_CHAT_LOG_SNAPSHOT_CHARS,
  deriveChatLogTitle,
  isChatLogSnapshot,
  isRegion,
} from "@/lib/strategy/chatLogEntry";
import {
  deleteStrategyChatLog,
  listStrategyChatLog,
  readStrategyChatLogSnapshot,
  upsertStrategyChatLog,
} from "@/lib/server/strategyChatLog";

export const dynamic = "force-dynamic";

type Params = { params: { sessionId: string } };

function validSessionId(value: string): boolean {
  return value.length > 0 && value.length <= MAX_CHAT_LOG_SESSION_ID_CHARS;
}

// 대화 하나의 복원 스냅샷 — 목록에서 항목을 열 때 받는다.
export async function GET(_request: NextRequest, { params }: Params) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!validSessionId(params.sessionId)) {
    return NextResponse.json({ error: "Invalid session id" }, { status: 400 });
  }
  try {
    const snapshot = await readStrategyChatLogSnapshot(user.id, params.sessionId);
    if (snapshot === null) return NextResponse.json({ error: "Not found" }, { status: 404 });
    return new NextResponse(`{"snapshot":${snapshot}}`, {
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Strategy chat log read error:", error);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}

// 대화 저장(upsert). 본문 = { region, snapshot }. 제목·메시지 수는 서버가 스냅샷에서 뽑는다.
// 저장 뒤 상한(30건)을 넘는 가장 오래 쓰지 않은 항목을 지우고 갱신된 목록을 돌려준다.
export async function PUT(request: NextRequest, { params }: Params) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!validSessionId(params.sessionId)) {
    return NextResponse.json({ error: "Invalid session id" }, { status: 400 });
  }

  let body: { region?: unknown; snapshot?: unknown };
  try {
    body = (await request.json()) as { region?: unknown; snapshot?: unknown };
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  if (!isRegion(body.region) || !isChatLogSnapshot(body.snapshot)) {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }
  if (body.snapshot.messages.length === 0) {
    return NextResponse.json({ error: "Empty conversation" }, { status: 400 });
  }
  const snapshot = JSON.stringify(body.snapshot);
  if (snapshot.length > MAX_CHAT_LOG_SNAPSHOT_CHARS) {
    return NextResponse.json({ error: "Snapshot too large" }, { status: 413 });
  }

  try {
    await upsertStrategyChatLog({
      userId: user.id,
      sessionId: params.sessionId,
      region: body.region,
      title: deriveChatLogTitle(body.snapshot.messages),
      messageCount: body.snapshot.messages.length,
      snapshot,
    });
    const entries = await listStrategyChatLog(user.id);
    return NextResponse.json({ entries });
  } catch (error) {
    console.error("Strategy chat log write error:", error);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}

export async function DELETE(_request: NextRequest, { params }: Params) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  if (!validSessionId(params.sessionId)) {
    return NextResponse.json({ error: "Invalid session id" }, { status: 400 });
  }
  try {
    await deleteStrategyChatLog(user.id, params.sessionId);
    const entries = await listStrategyChatLog(user.id);
    return NextResponse.json({ entries });
  } catch (error) {
    console.error("Strategy chat log delete error:", error);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
