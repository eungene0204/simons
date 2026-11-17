import { describe, expect, it } from "vitest";
import { isReleasedDeletedEmail, releasedDeletedEmail } from "./deletedAccountEmail";

describe("releasedDeletedEmail", () => {
  it("원래 주소를 deleted-<id>: 접두로 바꾼다", () => {
    expect(releasedDeletedEmail(42, "a@b.com")).toBe("deleted-42:a@b.com");
  });
  it("이미 해제된 주소는 그대로 둔다(멱등)", () => {
    expect(releasedDeletedEmail(42, "deleted-42:a@b.com")).toBe("deleted-42:a@b.com");
  });
  it("일반 주소는 해제된 주소로 보지 않는다", () => {
    expect(isReleasedDeletedEmail("deleted@b.com")).toBe(false);
    expect(isReleasedDeletedEmail("deleted-3:a@b.com")).toBe(true);
  });
});
