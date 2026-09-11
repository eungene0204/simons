import '@testing-library/jest-dom';

// jsdom에는 ResizeObserver가 없어 recharts ResponsiveContainer가 크래시한다 — 최소 스텁 제공.
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

// 저장 필드 암호화 키(lib/server/fieldCrypto) — 운영과 같은 경로를 타도록 테스트 전용 키를 넣는다.
// 이 값이 없으면 결제 확정 경로가 "키 없음"으로 먼저 멈춘다(의도된 fail closed).
process.env.FIELD_ENCRYPTION_KEY ||= Buffer.alloc(32, 7).toString('base64');
