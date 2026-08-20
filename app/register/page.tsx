import { redirect } from "next/navigation";
import {
  isEmailSignupEnabled,
  isEmailVerificationRequired,
} from "@/lib/server/email-verification";
import RegisterForm from "./RegisterForm";

// 이메일 가입은 테스트용 한시 기능 — 킬 스위치(EMAIL_SIGNUP_ENABLED=off)가 켜지면
// 종전 동작(랜딩 리다이렉트)으로 돌아간다. 플래그는 요청 시점에 읽어야 하므로 동적 렌더.
export const dynamic = "force-dynamic";

export default function RegisterPage() {
  if (!isEmailSignupEnabled()) {
    redirect("/");
  }
  return <RegisterForm verificationRequired={isEmailVerificationRequired()} />;
}
