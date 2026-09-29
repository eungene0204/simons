import { beforeEach, describe, expect, it, vi } from "vitest";
import { getStockNameMap, loadStockMasterNameMap } from "./krx-stocks";
import { resolveTrackedDisplayNames } from "@/components/virtual-account/stockDisplayNames";

const { files, versions } = vi.hoisted(() => ({
  files: {} as Record<string, unknown>, versions: {} as Record<string, number>,
}));
vi.mock("fs/promises", () => ({
  readFile: vi.fn(async (path: string) => {
    const file = path.split("/").at(-1)!;
    if (!(file in files)) throw new Error("missing file");
    return JSON.stringify(files[file]);
  }),
  stat: vi.fn(async (path: string) => {
    const file = path.split("/").at(-1)!;
    if (!(file in files)) throw new Error("missing file");
    return { mtimeMs: versions[file] ?? 1, size: 100 };
  }),
}));

describe("delisted stock names", () => {
  beforeEach(() => {
    for (const key of Object.keys(files)) delete files[key];
    for (const key of Object.keys(versions)) delete versions[key];
    global.__stockNameMapCache = undefined;
    files["korea-stocks.json"] = [{ symbol: "005930", name: "삼성전자" }];
    files["stock-master.json"] = { stocks: [{ symbol: "005390", name: "신성통상" }] };
    files["delisted-stocks.json"] = { symbols: ["005390", "140910"], names: { "005390": "신성통상", "140910": "에이리츠" } };
  });

  it("resolves code-only monitoring entries from history and preserved names", async () => {
    const metadata = await getStockNameMap();
    expect(resolveTrackedDisplayNames([{ symbol: "005390", name: "005390" }], metadata))
      .toEqual([{ symbol: "005390", name: "신성통상" }]);
    expect(metadata["140910"]).toBe("에이리츠");
    expect(metadata["005930"]).toBe("삼성전자");
  });

  it("keeps ledger names when the historical master is missing", async () => {
    delete files["stock-master.json"];
    expect((await loadStockMasterNameMap())["005390"]).toBe("신성통상");
  });

  it("reloads names when the ledger changes without a current-list change", async () => {
    await getStockNameMap();
    files["delisted-stocks.json"] = { symbols: ["005390"], names: { "005390": "보존된 새 이름" } };
    versions["delisted-stocks.json"] = 2;
    expect((await getStockNameMap())["005390"]).toBe("보존된 새 이름");
  });

  it("prefers current names and supports old code-only ledgers", async () => {
    files["delisted-stocks.json"] = { symbols: ["005390"] };
    files["stock-master.json"] = { stocks: [{ symbol: "005930", name: "이전 사명" }, { symbol: "005390", name: "신성통상" }] };
    expect(await getStockNameMap()).toMatchObject({ "005930": "삼성전자", "005390": "신성통상" });
  });
});
