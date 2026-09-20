"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { METRIC_PATH_GROUPS, suggestedExpression } from "@/lib/metric-paths";
import type { AssertionDraft } from "@/lib/scenario-document";
import type { Severity } from "@reslab/api-client";

const SEVERITIES: readonly Severity[] = ["info", "low", "medium", "high", "critical"];

/** Assertion rows plus a browser of the metric paths the analysis exposes. */
export function AssertionEditor({
  assertions,
  onChange,
}: {
  assertions: readonly AssertionDraft[];
  onChange: (next: AssertionDraft[]) => void;
}) {
  const [helperOpen, setHelperOpen] = useState(false);

  const update = (index: number, patch: Partial<AssertionDraft>) =>
    onChange(
      assertions.map((assertion, position) =>
        position === index ? { ...assertion, ...patch } : assertion,
      ),
    );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Label>Assertions</Label>
        <Button
          variant="ghost"
          size="xs"
          onClick={() =>
            onChange([
              ...assertions,
              {
                expression: "safety.loss_of_control == false",
                severity: "critical",
                description: "",
              },
            ])
          }
        >
          <Plus size={10} aria-hidden />
          Add assertion
        </Button>
        <Button
          variant="ghost"
          size="xs"
          aria-expanded={helperOpen}
          onClick={() => setHelperOpen(!helperOpen)}
        >
          {helperOpen ? "Hide metric paths" : "Show metric paths"}
        </Button>
      </div>

      {assertions.length === 0 ? (
        <p className="text-[11px] text-dim">
          No assertion. A scenario without a critical assertion still gets a score, but no hard gate
          beyond control authority and run completion.
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {assertions.map((assertion, index) => (
            <li key={index} className="grid grid-cols-[2.4fr_0.9fr_2fr_auto] gap-1.5">
              <Input
                value={assertion.expression}
                aria-label="Assertion expression"
                className="mono"
                onChange={(element) => update(index, { expression: element.target.value })}
              />
              <Select
                value={assertion.severity}
                onValueChange={(value) => update(index, { severity: value as Severity })}
              >
                <SelectTrigger aria-label="Assertion severity">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEVERITIES.map((severity) => (
                    <SelectItem key={severity} value={severity}>
                      {severity}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                value={assertion.description}
                aria-label="Assertion description"
                placeholder="optional"
                onChange={(element) => update(index, { description: element.target.value })}
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Remove assertion"
                onClick={() => onChange(assertions.filter((_, position) => position !== index))}
              >
                <Trash2 size={11} aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {helperOpen ? (
        <div className="rounded-sm border border-border bg-panel-2 p-2">
          <p className="mb-1.5 text-[10.5px] text-dim">
            Known metric paths. Selecting one appends an assertion with a suggested comparison.
            Duration literals accept a unit, for example 10s.
          </p>
          <div className="grid max-h-[220px] grid-cols-3 gap-3 overflow-y-auto">
            {METRIC_PATH_GROUPS.map((group) => (
              <section key={group.group}>
                <h4 className="panel-title mb-1 text-[9px]">{group.group}</h4>
                <ul className="flex flex-col gap-0.5">
                  {group.paths.map((path) => (
                    <li key={path.path}>
                      <button
                        type="button"
                        title={path.description}
                        disabled={path.path.includes("<")}
                        onClick={() =>
                          onChange([
                            ...assertions,
                            {
                              expression: suggestedExpression(path),
                              severity: "medium",
                              description: "",
                            },
                          ])
                        }
                        className="mono w-full truncate text-left text-[10.5px] text-muted transition-colors hover:text-info disabled:cursor-default disabled:text-dim"
                      >
                        {path.path}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
