/**
 * 브라우저에 남는 전략연구소 대화(로그·스냅샷)는 로그인 계정 하나의 것이어야 한다.
 * 2026-09-14 사고: 게스트 계정으로 들어갔더니 같은 브라우저에서 먼저 쓰던 계정의
 * 대화 기록 30건이 그대로 보였다 — 저장소에 계정 구분이 없었다.
 */
import { afterEach, describe, expect, it } from "vitest";

import {
  STRATEGY_CHAT_LOG_KEY,
  STRATEGY_CHAT_OWNER_KEY,
  chatStorageOwnerOf,
  clearStrategyChatStorage,
  reconcileStrategyChatStorage,
} from "./strategyChatStorage";
import { STRATEGY_CHAT_STATE_KEY } from "./strategyTemplateSession";

function seedAs(owner: string | null) {
  localStorage.setItem(STRATEGY_CHAT_LOG_KEY, '[{"id":"a"}]');
  sessionStorage.setItem(STRATEGY_CHAT_STATE_KEY, '{"messages":[]}');
  if (owner !== null) {
    localStorage.setItem(STRATEGY_CHAT_OWNER_KEY, owner);
    sessionStorage.setItem(STRATEGY_CHAT_OWNER_KEY, owner);
  }
}

describe("전략연구소 대화 저장소 주인 대조", () => {
  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("주인 표식은 로그인 사용자 id, 비로그인·id 없음은 빈 문자열이다", () => {
    expect(chatStorageOwnerOf({ id: 42 })).toBe("42");
    expect(chatStorageOwnerOf(null)).toBe("");
    expect(chatStorageOwnerOf({ name: "x" } as { id?: number })).toBe("");
  });

  it("같은 계정이면 대화를 그대로 둔다", () => {
    seedAs("1");
    reconcileStrategyChatStorage("1");
    expect(localStorage.getItem(STRATEGY_CHAT_LOG_KEY)).toBe('[{"id":"a"}]');
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBe('{"messages":[]}');
  });

  it("다른 계정이면 대화 로그와 스냅샷을 지우고 주인을 바꿔 적는다", () => {
    seedAs("1");
    reconcileStrategyChatStorage("2");
    expect(localStorage.getItem(STRATEGY_CHAT_LOG_KEY)).toBeNull();
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
    expect(localStorage.getItem(STRATEGY_CHAT_OWNER_KEY)).toBe("2");
    expect(sessionStorage.getItem(STRATEGY_CHAT_OWNER_KEY)).toBe("2");
  });

  it("주인 표식이 없는(수정 전에 저장된) 대화도 남의 것으로 보고 지운다", () => {
    seedAs(null);
    reconcileStrategyChatStorage("1");
    expect(localStorage.getItem(STRATEGY_CHAT_LOG_KEY)).toBeNull();
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
  });

  it("비로그인이면 무조건 지운다 — 비로그인은 대화를 시작할 수 없으므로 남은 대화는 남의 것", () => {
    seedAs("1");
    reconcileStrategyChatStorage("");
    expect(localStorage.getItem(STRATEGY_CHAT_LOG_KEY)).toBeNull();
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
    expect(localStorage.getItem(STRATEGY_CHAT_OWNER_KEY)).toBeNull();
  });

  it("저장소마다 따로 대조한다 — 다른 탭에서 이미 새 계정으로 바뀐 로그와 이 탭에 남은 옛 스냅샷", () => {
    localStorage.setItem(STRATEGY_CHAT_LOG_KEY, "[]");
    localStorage.setItem(STRATEGY_CHAT_OWNER_KEY, "2");
    sessionStorage.setItem(STRATEGY_CHAT_STATE_KEY, "{}");
    sessionStorage.setItem(STRATEGY_CHAT_OWNER_KEY, "1");
    reconcileStrategyChatStorage("2");
    expect(localStorage.getItem(STRATEGY_CHAT_LOG_KEY)).toBe("[]");
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
  });

  it("로그아웃 정리는 대화 데이터와 주인 표식을 모두 지운다", () => {
    seedAs("1");
    clearStrategyChatStorage();
    expect(localStorage.getItem(STRATEGY_CHAT_LOG_KEY)).toBeNull();
    expect(localStorage.getItem(STRATEGY_CHAT_OWNER_KEY)).toBeNull();
    expect(sessionStorage.getItem(STRATEGY_CHAT_STATE_KEY)).toBeNull();
    expect(sessionStorage.getItem(STRATEGY_CHAT_OWNER_KEY)).toBeNull();
  });
});
