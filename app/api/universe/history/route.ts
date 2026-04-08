import { NextResponse } from "next/server";
import { loadUniverseHistory, getUniverseOverview } from "@/lib/universe-history";

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
