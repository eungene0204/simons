import { mapAccount } from '@/lib/server/virtualAccountDetail';

// '전략공유' 화면(2026-10-20)의 카드 데이터. 공개 전략마다 그 전략을 쓰는 '공개 계좌'의 수익률만 싣는다 —
// 비공개 계좌의 성과는 전략이 공개여도 내보내지 않는다. 소유자 정보·전략 ID·상세 규칙은 싣지 않는다.

export interface SharedStrategyAccount {
  id: string;
  name: string;
  currency: 'KRW' | 'USD';
  status: string;
  returnPct: number;
  createdAt: string;
}

export interface SharedStrategyCard {
  key: string;
  name: string;
  description: string | null;
  // 전략 조건 표시용 DSL(카드가 buildStrategySummaryFromDsl로 라벨을 만든다). 전략 ID·소유자 필드는 뺀다.
  settings: Record<string, unknown> | null;
  // 공개 계좌 수익률의 평균. 공개 계좌가 없으면 null.
  avgReturnPct: number | null;
  accounts: SharedStrategyAccount[];
  updatedAt: string;
}

type StrategyRow = {
  id: string;
  userId: number | null;
  name: string;
  description: string | null;
  settings: string;
  updatedAt: Date;
};

function publicSettings(raw: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    // 전략 ID(strategy_id)와, 유니버스에서 풀어 낸 종목 코드 목록(symbols — 길고 조건이 아님)은 뺀다.
    const { id: _id, userId: _userId, strategy_id: _strategyId, symbols: _symbols, ...rest } =
      parsed as Record<string, unknown>;
    return rest;
  } catch {
    return null;
  }
}

export function buildSharedStrategyCards(
  strategies: StrategyRow[],
  publicAccounts: any[],
  settlementValues: Record<string, number>
): SharedStrategyCard[] {
  const cards = strategies.map((s, index) => {
    // 같은 소유자의 계좌만 — 전략 ID는 설정 해시라 다른 사용자의 같은 설정과 섞일 수 있다.
    const accounts = publicAccounts
      .filter((a) => a.strategyId === s.id && a.userId === s.userId)
      .map((a): SharedStrategyAccount => {
        const mapped = mapAccount(a, {}, {}, settlementValues[a.id]);
        const contributed = mapped.totalContributed;
        return {
          id: mapped.id,
          name: mapped.name,
          currency: mapped.currency,
          status: mapped.status,
          returnPct: contributed > 0 ? ((mapped.totalValue - contributed) / contributed) * 100 : 0,
          createdAt: mapped.createdAt,
        };
      });
    const avgReturnPct =
      accounts.length > 0 ? accounts.reduce((sum, a) => sum + a.returnPct, 0) / accounts.length : null;
    return {
      key: `s${index}`,
      name: s.name,
      description: s.description ?? null,
      settings: publicSettings(s.settings),
      avgReturnPct,
      accounts: accounts.sort((a, b) => b.returnPct - a.returnPct),
      updatedAt: s.updatedAt.toISOString(),
    };
  });

  // 수익률 순(2026-10-20 사용자 지시) — 공개 계좌가 없는 전략은 뒤로.
  return cards.sort((a, b) => {
    if (a.avgReturnPct == null) return b.avgReturnPct == null ? 0 : 1;
    if (b.avgReturnPct == null) return -1;
    return b.avgReturnPct - a.avgReturnPct;
  });
}
