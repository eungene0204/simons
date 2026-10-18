import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getStockNameMap, loadStockMasterNameMap } from "./krx-stocks";
import { resolveTrackedDisplayNames } from "@/components/virtual-account/stockDisplayNames";

// 모킹 없이 임시 디렉터리에 실제 파일을 쓴다. `vi.mock("fs/promises")`는 함수 안의 동적
// `import("fs/promises")`에 부하 상태에서 간헐적으로 적용되지 않아(실제 data/*.json을 읽음) 이 테스트가
// 전체 실행에서 무작위로 실패했다.
let dir: string;
const put = (file: string, value: unknown) => fs.writeFileSync(path.join(dir, "data", file), JSON.stringify(value));
const remove = (file: string) => fs.rmSync(path.join(dir, "data", file));

describe("delisted stock names", () => {
  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "krx-stocks-"));
    fs.mkdirSync(path.join(dir, "data"));
    vi.spyOn(process, "cwd").mockReturnValue(dir);
    global.__stockNameMapCache = undefined;
    put("korea-stocks.json", [{ symbol: "005930", name: "삼성전자" }]);
    put("stock-master.json", { stocks: [{ symbol: "005390", name: "신성통상" }] });
    put("delisted-stocks.json", { symbols: ["005390", "140910"], names: { "005390": "신성통상", "140910": "에이리츠" } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("resolves code-only monitoring entries from history and preserved names", async () => {
    const metadata = await getStockNameMap();
    expect(resolveTrackedDisplayNames([{ symbol: "005390", name: "005390" }], metadata))
      .toEqual([{ symbol: "005390", name: "신성통상" }]);
    expect(metadata["140910"]).toBe("에이리츠");
    expect(metadata["005930"]).toBe("삼성전자");
  });

  it("keeps ledger names when the historical master is missing", async () => {
    remove("stock-master.json");
    expect((await loadStockMasterNameMap())["005390"]).toBe("신성통상");
  });

  it("reloads names when the ledger changes without a current-list change", async () => {
    await getStockNameMap();
    put("delisted-stocks.json", { symbols: ["005390"], names: { "005390": "보존된 새 이름" } });
    expect((await getStockNameMap())["005390"]).toBe("보존된 새 이름");
  });

  it("prefers current names and supports old code-only ledgers", async () => {
    put("delisted-stocks.json", { symbols: ["005390"] });
    put("stock-master.json", { stocks: [{ symbol: "005930", name: "이전 사명" }, { symbol: "005390", name: "신성통상" }] });
    expect(await getStockNameMap()).toMatchObject({ "005930": "삼성전자", "005390": "신성통상" });
  });
});
