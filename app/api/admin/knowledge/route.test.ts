// @ts-nocheck
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import path from "path";

// 지식그래프 학습 검토 API(FR-STR-070b) — 권한 게이트(404 은닉)·엣지 승인/반려·
// 용어 삭제가 어휘집 파일(SOT)에 원자적으로 반영되고 감사 로그를 남기는지 검증한다.

const requireAdmin = vi.fn();
const writeAuditLog = vi.fn();

vi.mock("@/lib/server/adminAuth", () => ({
  requireAdmin: (...a) => requireAdmin(...a),
  writeAuditLog: (...a) => writeAuditLog(...a),
}));

let GET;
let PATCH;
let dir;
let lexPath;

const LEXICON = {
  cowos: {
    term: "CoWoS",
    definition: "첨단 반도체 패키징 기술",
    sector: "반도체",
    searched_at: "2026-07-25T00:00:00+00:00",
    sources: [{ title: "CoWoS", link: "https://a.example/1" }],
    edges: [
      { type: "related_to", target: "hbm", target_name: "HBM", support: 2, status: "verified", evidence: [] },
      { type: "uses", target: "gpu", target_name: "GPU", support: 1, status: "pending", evidence: [] },
    ],
  },
};

beforeEach(async () => {
  vi.clearAllMocks();
  dir = mkdtempSync(path.join(tmpdir(), "lex-"));
  lexPath = path.join(dir, "term_lexicon.json");
  writeFileSync(lexPath, JSON.stringify(LEXICON), "utf-8");
  process.env.TERM_LEXICON_PATH = lexPath;
  ({ GET, PATCH } = await import("./route"));
});

afterEach(() => {
  delete process.env.TERM_LEXICON_PATH;
  rmSync(dir, { recursive: true, force: true });
});

const admin = { id: 1, email: "admin@example.com", name: "Admin" };

function patchReq(body) {
  return { json: async () => body };
}

function readLexicon() {
  return JSON.parse(readFileSync(lexPath, "utf-8"));
}

describe("/api/admin/knowledge", () => {
  it("비관리자는 GET/PATCH 모두 404 (존재 자체를 숨김)", async () => {
    requireAdmin.mockResolvedValue(null);
    expect((await GET()).status).toBe(404);
    expect((await PATCH(patchReq({ action: "rejectEdge", key: "cowos" }))).status).toBe(404);
  });

  it("GET은 학습 용어·엣지 목록을 반환한다", async () => {
    requireAdmin.mockResolvedValue(admin);
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.terms).toHaveLength(1);
    expect(body.terms[0].term).toBe("CoWoS");
    expect(body.terms[0].edges).toHaveLength(2);
  });

  it("rejectEdge는 verified 엣지를 rejected로 바꾸고 감사 로그를 남긴다", async () => {
    requireAdmin.mockResolvedValue(admin);
    const res = await PATCH(patchReq({ action: "rejectEdge", key: "cowos", target: "hbm", type: "related_to" }));
    expect(res.status).toBe(200);
    const saved = readLexicon();
    expect(saved.cowos.edges[0].status).toBe("rejected");
    expect(saved.cowos.edges[1].status).toBe("pending"); // 다른 엣지는 불변
    expect(writeAuditLog).toHaveBeenCalledWith(admin, expect.objectContaining({ action: "knowledge.rejectEdge" }));
  });

  it("approveEdge는 pending 엣지를 verified로 승격한다", async () => {
    requireAdmin.mockResolvedValue(admin);
    await PATCH(patchReq({ action: "approveEdge", key: "cowos", target: "gpu", type: "uses" }));
    expect(readLexicon().cowos.edges[1].status).toBe("verified");
  });

  it("deleteTerm은 용어를 어휘집에서 제거한다 (재검색으로 재학습 가능)", async () => {
    requireAdmin.mockResolvedValue(admin);
    await PATCH(patchReq({ action: "deleteTerm", key: "cowos" }));
    expect(readLexicon()).toEqual({});
    expect(writeAuditLog).toHaveBeenCalledWith(admin, expect.objectContaining({ action: "knowledge.deleteTerm" }));
  });

  it("addEdge는 수동 verified 엣지를 근거와 함께 추가한다 (FR-STR-070b ⑦)", async () => {
    requireAdmin.mockResolvedValue(admin);
    const res = await PATCH(patchReq({
      action: "addEdge", key: "cowos", type: "related_company",
      target: "company:309960", targetName: "LB인베스트먼트", note: "하이브 초기 투자사",
    }));
    expect(res.status).toBe(200);
    const added = readLexicon().cowos.edges.at(-1);
    expect(added).toMatchObject({
      type: "related_company", target: "company:309960", target_name: "LB인베스트먼트",
      status: "verified", proposed_by: "manual", note: "하이브 초기 투자사",
    });
    expect(added.support).toBeUndefined(); // 출처 수 없음 — UI는 '수동 등록' 표기
    expect(writeAuditLog).toHaveBeenCalledWith(admin, expect.objectContaining({ action: "knowledge.addEdge" }));
  });

  it("addEdge는 중복 (type,target)·미허용 유형·필수 누락을 거절한다", async () => {
    requireAdmin.mockResolvedValue(admin);
    expect((await PATCH(patchReq({ action: "addEdge", key: "cowos", type: "related_to", target: "hbm" }))).status).toBe(409);
    expect((await PATCH(patchReq({ action: "addEdge", key: "cowos", type: "recommends", target: "hbm" }))).status).toBe(400);
    expect((await PATCH(patchReq({ action: "addEdge", key: "cowos", type: "related_to" }))).status).toBe(400);
  });

  it("없는 용어·엣지·액션은 각각 404/404/400", async () => {
    requireAdmin.mockResolvedValue(admin);
    expect((await PATCH(patchReq({ action: "deleteTerm", key: "없는키" }))).status).toBe(404);
    expect((await PATCH(patchReq({ action: "rejectEdge", key: "cowos", target: "없음", type: "uses" }))).status).toBe(404);
    expect((await PATCH(patchReq({ action: "unknown", key: "cowos" }))).status).toBe(400);
  });
});
