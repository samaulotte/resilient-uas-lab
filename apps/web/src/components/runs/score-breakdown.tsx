"use client";

import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { formatScore } from "@/lib/format";
import { cn, formatPercent } from "@/lib/utils";
import type { ScoreResult } from "@reslab/api-client";

/** Weighted dimensions with the points each contributed to the total. */
export function ScoreBreakdown({ score }: { score: ScoreResult }) {
  return (
    <Table>
      <THead>
        <tr>
          <TH>Dimension</TH>
          <TH className="w-[180px]">Score</TH>
          <TH className="text-right">Weight</TH>
          <TH className="text-right">Points</TH>
          <TH>Explanation</TH>
        </tr>
      </THead>
      <TBody>
        {score.dimensions.map((dimension) => {
          const inactive = dimension.weight === 0;
          return (
            <TR key={dimension.dimension} className={cn(inactive && "opacity-55")}>
              <TD className="whitespace-nowrap">{dimension.label}</TD>
              <TD>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-[104px] overflow-hidden rounded-full bg-panel-3">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        dimension.score >= 0.9
                          ? "bg-ok"
                          : dimension.score >= 0.6
                            ? "bg-warn"
                            : "bg-bad",
                      )}
                      style={{ width: `${Math.round(dimension.score * 100)}%` }}
                    />
                  </div>
                  <span className="mono text-[11px] text-muted">
                    {formatPercent(dimension.score, 1)}
                  </span>
                </div>
              </TD>
              <TD className="mono text-right text-muted">{dimension.weight}</TD>
              <TD className="mono text-right">{dimension.points.toFixed(2)}</TD>
              <TD className="text-muted">{dimension.explanation}</TD>
            </TR>
          );
        })}
        <TR className="bg-panel-2 font-semibold">
          <TD>Total</TD>
          <TD />
          <TD className="mono text-right text-muted">
            {score.dimensions.reduce((sum, dimension) => sum + dimension.weight, 0)}
          </TD>
          <TD className="mono text-right">{formatScore(score.total)}</TD>
          <TD className="text-muted">{score.reason}</TD>
        </TR>
      </TBody>
    </Table>
  );
}

export function HardGates({ score }: { score: ScoreResult }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {score.hard_gates.map((gate) => (
        <li
          key={gate.name}
          className={cn(
            "flex items-start justify-between gap-3 rounded-sm border px-2.5 py-1.5",
            gate.passed ? "border-ok/40 bg-ok-soft" : "border-bad/50 bg-bad-soft",
          )}
        >
          <span className="mono text-[11.5px] text-foreground">{gate.name}</span>
          <span className="flex-1 text-right text-[11.5px] text-muted">{gate.reason}</span>
          <Badge tone={gate.passed ? "ok" : "bad"} size="xs">
            {gate.passed ? "PASSED" : "FAILED"}
          </Badge>
        </li>
      ))}
    </ul>
  );
}
