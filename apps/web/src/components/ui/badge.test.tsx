import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ComponentStateBadge,
  EventKindBadge,
  ResultBadge,
  RunStateBadge,
} from "@/components/ui/badge";
import type { ComponentState } from "@reslab/api-client";

const TONE_CLASS: Record<string, string> = {
  ok: "text-ok",
  warn: "text-warn",
  bad: "text-bad",
  info: "text-info",
  dim: "text-muted",
};

describe("ComponentStateBadge", () => {
  it.each<[ComponentState, string]>([
    ["NOMINAL", "ok"],
    ["OPERATIONAL", "ok"],
    ["RECOVERED", "ok"],
    ["DEGRADED", "warn"],
    ["RECOVERING", "warn"],
    ["UNAVAILABLE", "bad"],
    ["FAILED", "bad"],
    ["UNKNOWN", "dim"],
  ])("maps %s to the %s tone", (state, tone) => {
    render(<ComponentStateBadge state={state} />);
    const badge = screen.getByText(state);
    expect(badge).toHaveClass(TONE_CLASS[tone] ?? "");
  });

  it("falls back to UNKNOWN when no observation is available", () => {
    render(<ComponentStateBadge state={undefined} />);
    expect(screen.getByText("UNKNOWN")).toHaveClass("text-muted");
  });
});

describe("RunStateBadge", () => {
  it("uses green only for a healthy run state", () => {
    const { unmount } = render(<RunStateBadge state="RUNNING" />);
    expect(screen.getByText("RUNNING")).toHaveClass("text-ok");
    unmount();
    render(<RunStateBadge state="FAILED" />);
    expect(screen.getByText("FAILED")).toHaveClass("text-bad");
  });

  it("keeps a cancelled run neutral rather than red", () => {
    render(<RunStateBadge state="CANCELLED" />);
    expect(screen.getByText("CANCELLED")).toHaveClass("text-muted");
  });
});

describe("ResultBadge", () => {
  it("marks a run that was never analyzed", () => {
    render(<ResultBadge result={null} />);
    expect(screen.getByText("NOT ANALYZED")).toHaveClass("text-muted");
  });

  it("uses green for passed and red for failed", () => {
    const { unmount } = render(<ResultBadge result="passed" />);
    expect(screen.getByText("PASSED")).toHaveClass("text-ok");
    unmount();
    render(<ResultBadge result="failed" />);
    expect(screen.getByText("FAILED")).toHaveClass("text-bad");
  });

  it("keeps an inconclusive result amber", () => {
    render(<ResultBadge result="inconclusive" />);
    expect(screen.getByText("INCONCLUSIVE")).toHaveClass("text-warn");
  });
});

describe("EventKindBadge", () => {
  it("shows the short code and explains the kind", () => {
    render(<EventKindBadge kind="OBSERVED_EFFECT" />);
    const badge = screen.getByText("OBS");
    expect(badge).toHaveAttribute(
      "title",
      "Observed effect: Component state change observed in the target",
    );
  });
});
