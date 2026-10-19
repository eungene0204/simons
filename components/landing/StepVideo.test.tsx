import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StepVideo } from "./StepVideo";

afterEach(() => vi.unstubAllGlobals());

describe("StepVideo", () => {
  it("points at the step's own files and is muted and looped", () => {
    const { container } = render(<StepVideo name="validate" label="검증 영상" />);
    const video = container.querySelector("video")!;
    expect(video.muted).toBe(true);
    expect(video).toHaveAttribute("loop");
    expect(video).toHaveAttribute("poster", "/videos/landing-validate-poster.jpg");
    expect(Array.from(video.querySelectorAll("source")).map((s) => s.getAttribute("src"))).toEqual([
      "/videos/landing-validate.webm",
      "/videos/landing-validate.mp4",
    ]);
  });

  it("plays only while it is on screen", () => {
    let notify: (entries: Array<{ isIntersecting: boolean }>) => void = () => undefined;
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(cb: typeof notify) { notify = cb; }
        observe() {}
        disconnect() {}
      },
    );
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    render(<StepVideo name="paper" label="모의투자 영상" />);

    notify([{ isIntersecting: true }]);
    expect(play).toHaveBeenCalledTimes(1);
    notify([{ isIntersecting: false }]);
    expect(pause).toHaveBeenCalled();
  });
});
