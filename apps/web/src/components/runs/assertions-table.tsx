"use client";

import { Badge, SeverityBadge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { AssertionResult } from "@reslab/api-client";

const OUTCOME_TONE = {
  passed: "ok",
  failed: "bad",
  not_evaluated: "dim",
} as const;

function formatOperand(value: number | boolean | null): string {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "boolean") return value ? "true" : "false";
  return Number.isInteger(value)
    ? String(value)
    : value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

/** Assertion outcomes exactly as the analysis evaluated them. */
export function AssertionsTable({ assertions }: { assertions: readonly AssertionResult[] }) {
  if (assertions.length === 0) {
    return <p className="px-3 py-4 text-[12px] text-muted">This scenario declares no assertion.</p>;
  }
  return (
    <Table>
      <THead>
        <tr>
          <TH>Expression</TH>
          <TH>Severity</TH>
          <TH>Outcome</TH>
          <TH className="text-right">Measured</TH>
          <TH className="text-right">Expected</TH>
          <TH>Explanation</TH>
        </tr>
      </THead>
      <TBody>
        {assertions.map((assertion, index) => (
          <TR key={`${assertion.expression}-${index}`}>
            <TD className="mono whitespace-nowrap">
              {assertion.expression}
              {assertion.description ? (
                <span className="mt-0.5 block max-w-[38ch] whitespace-normal text-[10.5px] text-dim">
                  {assertion.description}
                </span>
              ) : null}
            </TD>
            <TD>
              <SeverityBadge severity={assertion.severity} size="xs" />
            </TD>
            <TD>
              <Badge tone={OUTCOME_TONE[assertion.outcome]} size="xs">
                {assertion.outcome.replace("_", " ").toUpperCase()}
              </Badge>
            </TD>
            <TD className="mono text-right">{formatOperand(assertion.measured)}</TD>
            <TD className="mono text-right text-muted">
              {assertion.operator} {formatOperand(assertion.expected)}
            </TD>
            <TD className="text-muted">{assertion.explanation}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
