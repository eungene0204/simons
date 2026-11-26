import { describe, expect, it } from "vitest";
import { serializeSignupUtm, signupUtmFields, utmFromSearchParams } from "@/lib/signupUtm";

describe("signupUtm — 가입 유입 경로", () => {
  it("utm 세 칸을 읽어 쿠키 값으로 왕복한다", () => {
    const utm = utmFromSearchParams(new URLSearchParams("utm_source=x&utm_medium=social&utm_campaign=myth-23"));
    expect(utm).toEqual({ source: "x", medium: "social", campaign: "myth-23" });
    expect(signupUtmFields(encodeURIComponent(serializeSignupUtm(utm!)))).toEqual({
      signupUtmSource: "x",
      signupUtmMedium: "social",
      signupUtmCampaign: "myth-23",
    });
  });

  it("utm_source가 없으면 기록하지 않는다", () => {
    expect(utmFromSearchParams(new URLSearchParams("utm_medium=social"))).toBeNull();
  });

  it("허용 문자 밖의 값·깨진 쿠키는 버린다", () => {
    expect(utmFromSearchParams(new URLSearchParams("utm_source=<script>"))).toBeNull();
    expect(signupUtmFields("x|<b>|ok")).toEqual({ signupUtmSource: "x", signupUtmMedium: null, signupUtmCampaign: "ok" });
    expect(signupUtmFields("%E0%A4%A")).toEqual({});
    expect(signupUtmFields(undefined)).toEqual({});
  });

  it("64자를 넘으면 잘라서 저장한다", () => {
    const long = "a".repeat(100);
    expect(utmFromSearchParams(new URLSearchParams(`utm_source=${long}`))?.source).toHaveLength(64);
  });
});
