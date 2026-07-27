// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import KnowledgeTab from "../admin/KnowledgeTab";

// Knowledge 탭 서브탭(FR-STR-070c) — '학습 검토'(기존 검토 UI)와 'KG 시각화'
// (합성 그래프 뷰) 전환, 시각화의 범례·노드/엣지 카운트 표시를 검증한다.
// 캔버스 렌더링 자체는 jsdom(2d 컨텍스트 없음)에서 조용히 생략된다.

const TERMS = {
  terms: [
    {
      key: "cowos",
      term: "CoWoS",
      definition: "첨단 패키징",
      sector: "반도체",
      searched_at: "2026-07-25T00:00:00+00:00",
      sources: [],
      edges: [],
    },
    {
      key: "다이어트",
      term: "다이어트",
      definition: "체중 감량 산업",
      sector: null,
      searched_at: "2026-07-27T00:00:00+00:00",
      sources: [],
      edges: [
        {
          type: "related_company",
          target: "company:353190",
          target_name: "휴럼",
          support: 2,
          status: "verified",
          evidence: [],
        },
        {
          type: "related_to",
          target: "obesity-drug",
          target_name: "비만치료제",
          support: 1,
          status: "pending",
          evidence: [],
        },
      ],
    },
  ],
};

const GRAPH = {
  nodes: [
    {
      id: "hbm",
      name: "HBM",
      category: "technology",
      description: "고대역폭 메모리",
      synonyms: ["고대역폭 메모리"],
    },
    { id: "sector:반도체", name: "반도체", category: "industry" },
    { id: "company:000660", name: "SK하이닉스", category: "company" },
    { id: "learned:cowos", name: "CoWoS", category: "learned" },
  ],
  edges: [
    { source: "hbm", type: "belongs_to", target: "sector:반도체" },
    { source: "hbm", type: "produced_by", target: "company:000660" },
  ],
  issues: [],
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = String(url).includes("/graph") ? GRAPH : TERMS;
      return { ok: true, json: async () => body };
    })
  );
});

describe("KnowledgeTab 서브탭", () => {
  it("기본은 학습 검토, 학습 용어가 표시된다", async () => {
    render(<KnowledgeTab />);
    expect(await screen.findByText("CoWoS")).toBeInTheDocument();
    expect(screen.getByText("학습 검토")).toBeInTheDocument();
    expect(screen.getByText("KG 시각화")).toBeInTheDocument();
  });

  it("학습 검토 용어 박스는 기본 접힘 — 엣지 수·검토 대기 배지만 보이고 클릭 시 펼쳐진다", async () => {
    render(<KnowledgeTab />);
    expect(await screen.findByText("다이어트")).toBeInTheDocument();
    expect(screen.getByText("엣지 2")).toBeInTheDocument();
    expect(screen.getByText("검토 대기 1")).toBeInTheDocument();
    expect(screen.queryByText(/휴럼/)).not.toBeInTheDocument(); // 접힘: 엣지 목록 숨김

    fireEvent.click(screen.getByText("다이어트"));
    expect(await screen.findByText(/휴럼/)).toBeInTheDocument();
    expect(screen.getByText(/비만치료제/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("다이어트"));
    expect(screen.queryByText(/휴럼/)).not.toBeInTheDocument(); // 다시 접힘
  });

  it("학습 검토 검색 — 용어·종목명으로 필터링하고 일치 항목은 자동으로 펼친다", async () => {
    render(<KnowledgeTab />);
    await screen.findByText("CoWoS");

    fireEvent.change(screen.getByPlaceholderText("용어·정의·종목명 검색"), {
      target: { value: "휴럼" }, // 엣지 대상 종목명 역조회
    });
    expect(screen.queryByText("CoWoS")).not.toBeInTheDocument(); // 필터링
    expect(screen.getByText("다이어트")).toBeInTheDocument();
    expect(screen.getByText(/휴럼/)).toBeInTheDocument(); // 자동 펼침

    fireEvent.change(screen.getByPlaceholderText("용어·정의·종목명 검색"), {
      target: { value: "없는용어" },
    });
    expect(screen.getByText("일치하는 용어가 없습니다.")).toBeInTheDocument();
  });

  it("KG 시각화 탭 전환 시 그래프를 조회해 범례·카운트를 표시한다", async () => {
    render(<KnowledgeTab />);
    fireEvent.click(screen.getByText("KG 시각화"));

    await waitFor(() => {
      expect(screen.getByText(/노드 4 · 엣지 2/)).toBeInTheDocument();
    });
    // 그룹 범례(카운트 포함) — 색 단독 식별을 피하는 2차 인코딩의 일부
    expect(screen.getByText(/개념·테마 1/)).toBeInTheDocument();
    expect(screen.getByText(/섹터 1/)).toBeInTheDocument();
    expect(screen.getByText(/상장사 1/)).toBeInTheDocument();
    expect(screen.getByText(/학습 용어 1/)).toBeInTheDocument();
    expect(
      (global.fetch as any).mock.calls.some((c) => String(c[0]) === "/api/admin/knowledge/graph")
    ).toBe(true);
  });

  it("검색창에 이름 부분일치 노드가 드롭다운으로 표시된다", async () => {
    render(<KnowledgeTab />);
    fireEvent.click(screen.getByText("KG 시각화"));
    await waitFor(() => expect(screen.getByText(/노드 4 · 엣지 2/)).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("노드 검색 (이름·별칭)"), {
      target: { value: "SK" },
    });
    expect(await screen.findByText("SK하이닉스")).toBeInTheDocument();
  });

  it("별칭(synonyms)으로도 검색된다", async () => {
    render(<KnowledgeTab />);
    fireEvent.click(screen.getByText("KG 시각화"));
    await waitFor(() => expect(screen.getByText(/노드 4 · 엣지 2/)).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("노드 검색 (이름·별칭)"), {
      target: { value: "고대역폭" },
    });
    // 드롭다운 항목의 노드명(HBM)과 범례의 그룹 개수(반도체 1)가 겹치지 않게 노드명으로 확인
    const options = await screen.findAllByText("HBM");
    expect(options.length).toBeGreaterThan(0);
  });

  it("일치하는 노드가 없으면 안내 문구를 보여준다", async () => {
    render(<KnowledgeTab />);
    fireEvent.click(screen.getByText("KG 시각화"));
    await waitFor(() => expect(screen.getByText(/노드 4 · 엣지 2/)).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("노드 검색 (이름·별칭)"), {
      target: { value: "존재하지않는용어" },
    });
    expect(await screen.findByText("일치하는 노드 없음")).toBeInTheDocument();
  });

  it("드롭다운 항목을 클릭하면 검색창에 이름이 채워지고 드롭다운이 닫힌다", async () => {
    render(<KnowledgeTab />);
    fireEvent.click(screen.getByText("KG 시각화"));
    await waitFor(() => expect(screen.getByText(/노드 4 · 엣지 2/)).toBeInTheDocument());

    const input = screen.getByPlaceholderText("노드 검색 (이름·별칭)") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "SK" } });
    fireEvent.mouseDown(await screen.findByText("SK하이닉스"));

    expect(input.value).toBe("SK하이닉스");
    expect(screen.queryByText("일치하는 노드 없음")).not.toBeInTheDocument();
  });

  it("Enter 키로 첫 번째 검색 결과를 선택한다", async () => {
    render(<KnowledgeTab />);
    fireEvent.click(screen.getByText("KG 시각화"));
    await waitFor(() => expect(screen.getByText(/노드 4 · 엣지 2/)).toBeInTheDocument());

    const input = screen.getByPlaceholderText("노드 검색 (이름·별칭)") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "HBM" } });
    await screen.findByText("HBM", { selector: "span.truncate" });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(input.value).toBe("HBM");
  });

  it("상장사 범례는 토글 — 기본 '선택 시 표시', 클릭하면 '전체 표시'로 바뀐다", async () => {
    render(<KnowledgeTab />);
    fireEvent.click(screen.getByText("KG 시각화"));
    await waitFor(() => expect(screen.getByText(/노드 4 · 엣지 2/)).toBeInTheDocument());

    const toggle = screen.getByRole("button", { name: /상장사 1/ });
    expect(toggle.textContent).toContain("선택 시 표시");
    fireEvent.click(toggle);
    expect(toggle.textContent).toContain("전체 표시");
    fireEvent.click(toggle);
    expect(toggle.textContent).toContain("선택 시 표시");
  });

  it("그래프 조회 실패 시 에러를 표시한다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/graph")) {
          return { ok: false, status: 502, json: async () => ({ error: "백엔드 그래프 조회 실패" }) };
        }
        return { ok: true, json: async () => TERMS };
      })
    );
    render(<KnowledgeTab />);
    fireEvent.click(screen.getByText("KG 시각화"));
    expect(await screen.findByText("백엔드 그래프 조회 실패")).toBeInTheDocument();
  });
});
