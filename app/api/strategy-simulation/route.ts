import { noStoreJson } from "./response";
import { listPublicStrategies } from "@/lib/server/publicSimulation/access";
import { ensureFresh, getBaseline, presentOriginal } from "@/lib/server/publicSimulation/originals";

export const dynamic = "force-dynamic";

const CARD_CURVE_POINTS = 120;
const MAX_QUERY_LENGTH = 50;
const MAX_PAGE = 1000;

type Curve = { dates: string[]; returnPct: number[] };

// 카드 미니 그래프 — 첫·마지막 점을 포함해 등간격으로 줄인다(상세와 같은 저장 곡선에서).
function downsample(curve: Curve | undefined, max: number): Curve | undefined {
  if (!curve || !Array.isArray(curve.dates) || curve.dates.length <= max) return curve;
  const last = curve.dates.length - 1;
  const idx = [...new Set(Array.from({ length: max }, (_, i) => Math.round((i * last) / (max - 1))))];
  return { dates: idx.map((i) => curve.dates[i]), returnPct: idx.map((i) => curve.returnPct[i]) };
}

const pick = (source: Record<string, unknown> | undefined, keys: string[]) =>
  source ? Object.fromEntries(keys.filter((k) => k in source).map((k) => [k, source[k]])) : undefined;

// 예시 전략 목록 — 저장된 원본 결과만 읽는다. 낡은 항목은 백그라운드 갱신을 예약할 뿐 기다리지 않는다.
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const q = params.get("q")?.trim() || undefined;
  const pageRaw = params.get("page");
  const page = pageRaw === null ? 1 : Number(pageRaw);
  if (q && q.length > MAX_QUERY_LENGTH) return noStoreJson({ code: "INVALID_QUERY" }, 400);
  if (!Number.isInteger(page) || page < 1 || page > MAX_PAGE) return noStoreJson({ code: "INVALID_PAGE" }, 400);

  try {
    const [{ items, hasNext }, baseline] = await Promise.all([listPublicStrategies({ q, page }), getBaseline()]);
    const cards = items.map((item) => {
      ensureFresh(item, baseline);
      const view = presentOriginal(item, baseline) as Record<string, any>;
      return {
        publicId: item.row.id,
        name: item.name,
        description: item.description,
        randomAssumed: item.assumptions.some((a) => a.random),
        status: view.status,
        reason: view.reason,
        window: pick(view.window, ["requestedStart", "requestedEnd", "actualStart", "actualEnd", "dataAsOf", "stale", "limited"]),
        summary: pick(view.summary, ["totalReturnPct", "totalProfit", "maxDrawdownPct"]),
        curve: downsample(view.curve, CARD_CURVE_POINTS),
        computedAt: view.computedAt,
      };
    });
    return noStoreJson({
      items: cards,
      page,
      hasNext,
      baseline: baseline && pick(baseline as Record<string, unknown>, ["dataAsOf", "stale", "requestedStart", "requestedEnd"]),
    });
  } catch (error) {
    console.error("[strategy-simulation] list failed", error);
    return noStoreJson({ code: "LIST_FAILED" }, 500);
  }
}
