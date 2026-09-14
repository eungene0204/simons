import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { listStrategyChatLog } from "@/lib/server/strategyChatLog";

export const dynamic = "force-dynamic";

// 전략연구소 왼쪽 대화 로그 — 로그인 사용자의 지난 대화 목록(스냅샷 제외, 최근 사용 순, 최대 30건).
export async function GET() {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try {
    const entries = await listStrategyChatLog(user.id);
    return NextResponse.json({ entries });
  } catch (error) {
    console.error("Strategy chat log list error:", error);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
