import GuestLoginForm from "./GuestLoginForm";

// 게스트(테스터) 입장 — 운영자가 발급한 아이디·비밀번호로 로그인한다.
// 킬 스위치는 두지 않는다: 계정 발급 자체가 운영자 통제라 페이지가 열려 있어도 입장 조건이 늘지 않는다.
export default function GuestPage() {
  return <GuestLoginForm />;
}
