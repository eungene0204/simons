import { noStoreJson, PUBLIC_ID_PATTERN } from "../response";
import {
  findPublicStrategy, publicStrategyFields, snapshotFromSettings, snapshotHash,
} from "@/lib/server/publicSimulation/access";
import { ensureFresh, getBaseline, presentOriginal } from "@/lib/server/publicSimulation/originals";

export const dynamic = "force-dynamic";

// 공개 상세 — 예시 등록부에 없는 키는 404.
export async function GET(_request: Request, { params }: { params: { publicId: string } }) {
  if (!PUBLIC_ID_PATTERN.test(params.publicId)) return noStoreJson({ code: "NOT_FOUND" }, 404);
  try {
    const item = await findPublicStrategy(params.publicId);
    if (!item) return noStoreJson({ code: "NOT_FOUND" }, 404);
    const baseline = await getBaseline();
    ensureFresh(item, baseline);
    return noStoreJson({
      publicId: item.row.id,
      name: item.name,
      description: item.description,
      strategy: publicStrategyFields(item.settings),
      assumptions: item.assumptions,
      // 수정 실행 요청이 '지금 보는 원본'을 가리키는 값 — 설정이 바뀌면 달라진다.
      baseSnapshotHash: snapshotHash(snapshotFromSettings(item.settings)),
      original: presentOriginal(item, baseline),
      baseline,
    });
  } catch (error) {
    console.error("[strategy-simulation] detail failed", error);
    return noStoreJson({ code: "DETAIL_FAILED" }, 500);
  }
}
