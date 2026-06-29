import { NextResponse } from "next/server";
import { loadUniverseHistory, getUniverseOverview } from "@/lib/universe-history";

// 런타임 볼륨 data/universe-history.json을 읽으므로 정적 prerender 금지(빌드 시 파일 부재).
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const [history, overview] = await Promise.all([
      loadUniverseHistory(),
      getUniverseOverview(),
    ]);

    return NextResponse.json({
      updatedAt: history.updatedAt,
      latest: overview.latest,
      overview,
      history: history.entries,
    });
  } catch (error) {
    console.error("Failed to load universe history:", error);
    return NextResponse.json({ error: "Failed to load universe history" }, { status: 500 });
  }
}
