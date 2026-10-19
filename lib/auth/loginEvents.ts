// 화면 어디서든 상단 내비게이션의 로그인 모달(Google 로그인)을 열기 위한 창 이벤트.
// 모달 상태는 TopNavigation 안에 있어서 다른 화면은 이 이벤트로 요청한다.
// 받는 쪽이 모달을 열면 `preventDefault()`로 처리했음을 알린다 — 처리되지 않으면(내비게이션이 없는 화면 등)
// 보낸 쪽이 자기 대체 경로로 이동한다.
export const OPEN_LOGIN_EVENT = "nullstock:open-login";

/** 로그인 모달을 열어 달라고 요청한다. 받은 쪽이 있으면 true. */
export function requestLoginModal(): boolean {
  const event = new CustomEvent(OPEN_LOGIN_EVENT, { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}
