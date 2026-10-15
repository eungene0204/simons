import { describe, expect, it } from "vitest";

import { fromConfirmed, fromExecuted, fromSavedHistory } from "./snapshot";

const request = { entry: { conditions: [] }, exit: { conditions: [] }, risk: { max_positions: 5 } };
const parsed = { description: "x" } as never;

describe("snapshot selection", () => {
  it("confirmed needs both the parsed result and its request", () => {
    const ok = fromConfirmed({ sourceRef: "confirmed:m1#1", parsed, request, notices: ["n"] });
    expect(ok.origin).toBe("confirmed");
    expect(ok.schema).toBe("parsed+request");
    expect(ok.notices).toEqual(["n"]);
    expect(fromConfirmed({ sourceRef: "c", parsed: null, request }).origin).toBe("none");
    expect(fromConfirmed({ sourceRef: "c", parsed, request: null }).origin).toBe("none");
  });

  it("executed accepts only an engine request", () => {
    expect(fromExecuted({ sourceRef: "r", request }).schema).toBe("request");
    expect(fromExecuted({ sourceRef: "r", request: { symbols: [] } }).origin).toBe("none");
    expect(fromExecuted({ sourceRef: "r", request: null }).origin).toBe("none");
  });

  it("saved history uses result.executedRequest only; missing means no snapshot", () => {
    const withSnapshot = fromSavedHistory({ historyId: "h1", result: { executedRequest: request } });
    expect(withSnapshot.origin).toBe("executed");
    expect(withSnapshot.sourceRef).toBe("history:h1");
    const missing = fromSavedHistory({ historyId: "h2", result: {} });
    expect(missing.origin).toBe("none");
    expect(fromSavedHistory({ historyId: "h3", result: undefined }).origin).toBe("none");
  });
});
