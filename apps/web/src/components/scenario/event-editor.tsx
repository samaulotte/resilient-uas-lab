"use client";

import { ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FormRow, Input, Label } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { isDuration } from "@/lib/duration";
import type { EventDraft, ExpectationDraft, ParameterDraft } from "@/lib/scenario-document";
import { cn } from "@/lib/utils";
import type {
  CatalogEntry,
  ComponentState,
  Effect,
  EffectDescriptor,
} from "@reslab/api-client";

const STATES: readonly ComponentState[] = [
  "NOMINAL",
  "OPERATIONAL",
  "DEGRADED",
  "UNAVAILABLE",
  "FAILED",
  "RECOVERING",
  "RECOVERED",
];

export function parametersFor(descriptor: EffectDescriptor | undefined): ParameterDraft[] {
  return (descriptor?.parameters ?? []).map((parameter) => ({
    name: parameter.name,
    value: "",
    kind:
      parameter.type === "duration"
        ? "duration"
        : parameter.type === "integer"
          ? "integer"
          : parameter.type === "ratio"
            ? "ratio"
            : "number",
  }));
}

export function EventEditor({
  event,
  index,
  total,
  catalog,
  effects,
  selected,
  onSelect,
  onChange,
  onRemove,
  onMove,
}: {
  event: EventDraft;
  index: number;
  total: number;
  catalog: readonly CatalogEntry[];
  effects: readonly EffectDescriptor[];
  selected: boolean;
  onSelect: () => void;
  onChange: (next: EventDraft) => void;
  onRemove: () => void;
  onMove: (direction: -1 | 1) => void;
}) {
  const entry = catalog.find((item) => item.subsystem === event.subsystem);
  const descriptor = effects.find((item) => item.effect === event.effect);
  const durationDisabled = descriptor?.transient ?? false;
  const durationRequired = descriptor?.duration_required ?? false;
  const atValid = isDuration(event.at);
  const durationValid = !event.duration || isDuration(event.duration);

  const update = (patch: Partial<EventDraft>) => onChange({ ...event, ...patch });

  const changeEffect = (effect: Effect) => {
    const next = effects.find((item) => item.effect === effect);
    update({
      effect,
      parameters: parametersFor(next),
      duration: next?.transient ? "" : event.duration,
    });
  };

  const updateExpectation = (position: number, patch: Partial<ExpectationDraft>) => {
    const expect = event.expect.map((item, itemIndex) =>
      itemIndex === position ? { ...item, ...patch } : item,
    );
    update({ expect });
  };

  return (
    <li
      className={cn(
        "rounded-sm border bg-panel-2 p-2",
        selected ? "border-info/60" : "border-border",
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <button
          type="button"
          onClick={onSelect}
          className="mono text-[11.5px] text-info hover:underline"
          title="Select on the timeline"
        >
          {event.id || "unnamed"}
        </button>
        {entry?.critical ? (
          <Badge tone="warn" size="xs" title="Flight-critical subsystem">
            FLIGHT CRITICAL
          </Badge>
        ) : null}
        <div className="ml-auto flex items-center gap-0.5">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Move earlier in the list"
            disabled={index === 0}
            onClick={() => onMove(-1)}
          >
            <ChevronUp size={12} aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Move later in the list"
            disabled={index === total - 1}
            onClick={() => onMove(1)}
          >
            <ChevronDown size={12} aria-hidden />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Remove event" onClick={onRemove}>
            <Trash2 size={12} aria-hidden />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <FormRow label="Event id">
          <Input
            value={event.id}
            onChange={(element) => update({ id: element.target.value })}
            aria-label="Event id"
          />
        </FormRow>
        <FormRow label="At" hint={atValid ? undefined : "Use a duration such as 30s or 1m30s"}>
          <Input
            value={event.at}
            onChange={(element) => update({ at: element.target.value })}
            aria-label="Injection time"
            className={cn(!atValid && "border-bad/70")}
          />
        </FormRow>
        <FormRow label="Subsystem" className="col-span-2">
          <Select
            value={event.subsystem}
            onValueChange={(subsystem) => {
              const target = catalog.find((item) => item.subsystem === subsystem);
              const allowed = target?.effects ?? [];
              const effect = allowed.includes(event.effect) ? event.effect : allowed[0];
              const next = effects.find((item) => item.effect === effect);
              update({
                subsystem,
                ...(effect ? { effect } : {}),
                parameters: parametersFor(next),
              });
            }}
          >
            <SelectTrigger aria-label="Subsystem">
              <SelectValue placeholder="Select a subsystem" />
            </SelectTrigger>
            <SelectContent>
              {catalog
                .filter((item) => item.effects.length > 0)
                .map((item) => (
                  <SelectItem key={item.subsystem} value={item.subsystem}>
                    {item.name} ({item.subsystem})
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </FormRow>
        <FormRow label="Effect">
          <Select value={event.effect} onValueChange={(value) => changeEffect(value as Effect)}>
            <SelectTrigger aria-label="Effect">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(entry?.effects ?? []).map((effect) => (
                <SelectItem key={effect} value={effect}>
                  {effect}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FormRow>
        <FormRow
          label="Duration"
          hint={
            durationDisabled
              ? "Transient effect, the target recovers on its own"
              : durationRequired
                ? "Required for this effect"
                : "Empty means until the end of the scenario"
          }
        >
          <Input
            value={event.duration}
            disabled={durationDisabled}
            placeholder={durationRequired ? "required, e.g. 20s" : "until scenario end"}
            onChange={(element) => update({ duration: element.target.value })}
            aria-label="Effect duration"
            className={cn(
              (!durationValid || (durationRequired && !event.duration)) && "border-bad/70",
            )}
          />
        </FormRow>
        <FormRow label="Description" className="col-span-2">
          <Input
            value={event.description}
            onChange={(element) => update({ description: element.target.value })}
            aria-label="Event description"
            placeholder="What this disturbance represents"
          />
        </FormRow>
      </div>

      {descriptor && descriptor.parameters.length > 0 ? (
        <div className="mt-2">
          <Label className="mb-1 block">Effect parameters</Label>
          <div className="grid grid-cols-3 gap-2">
            {descriptor.parameters.map((spec) => {
              const current = event.parameters.find((item) => item.name === spec.name);
              const bounds = [
                spec.minimum !== null && spec.minimum !== undefined ? `min ${spec.minimum}` : null,
                spec.maximum !== null && spec.maximum !== undefined ? `max ${spec.maximum}` : null,
              ]
                .filter(Boolean)
                .join(", ");
              return (
                <FormRow
                  key={spec.name}
                  label={spec.name}
                  hint={bounds ? `${spec.description} (${bounds})` : spec.description}
                >
                  <Input
                    value={current?.value ?? ""}
                    placeholder={spec.type === "duration" ? "e.g. 2s" : spec.type}
                    inputMode={spec.type === "duration" ? "text" : "decimal"}
                    aria-label={`${spec.name} parameter`}
                    onChange={(element) => {
                      const value = element.target.value;
                      const exists = event.parameters.some((item) => item.name === spec.name);
                      const kind =
                        spec.type === "duration"
                          ? ("duration" as const)
                          : spec.type === "integer"
                            ? ("integer" as const)
                            : spec.type === "ratio"
                              ? ("ratio" as const)
                              : ("number" as const);
                      update({
                        parameters: exists
                          ? event.parameters.map((item) =>
                              item.name === spec.name ? { ...item, value, kind } : item,
                            )
                          : [...event.parameters, { name: spec.name, value, kind }],
                      });
                    }}
                  />
                </FormRow>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="mt-2">
        <div className="mb-1 flex items-center gap-2">
          <Label>Expectations</Label>
          <Button
            variant="ghost"
            size="xs"
            onClick={() =>
              update({
                expect: [
                  ...event.expect,
                  { subsystem: event.subsystem, state: "DEGRADED", within: "5s", description: "" },
                ],
              })
            }
          >
            <Plus size={10} aria-hidden />
            Add expectation
          </Button>
        </div>
        {event.expect.length === 0 ? (
          <p className="text-[10.5px] text-dim">
            No declared expectation. Expectations are verified against observations, never assumed.
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {event.expect.map((expectation, position) => (
              <li key={position} className="grid grid-cols-[1.6fr_1fr_0.7fr_1.6fr_auto] gap-1.5">
                <Select
                  value={expectation.subsystem}
                  onValueChange={(value) => updateExpectation(position, { subsystem: value })}
                >
                  <SelectTrigger aria-label="Expected subsystem">
                    <SelectValue placeholder="Subsystem" />
                  </SelectTrigger>
                  <SelectContent>
                    {catalog.map((item) => (
                      <SelectItem key={item.subsystem} value={item.subsystem}>
                        {item.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select
                  value={expectation.state}
                  onValueChange={(value) =>
                    updateExpectation(position, { state: value as ComponentState })
                  }
                >
                  <SelectTrigger aria-label="Expected state">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATES.map((state) => (
                      <SelectItem key={state} value={state}>
                        {state}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={expectation.within}
                  aria-label="Within"
                  onChange={(element) =>
                    updateExpectation(position, { within: element.target.value })
                  }
                  className={cn(!isDuration(expectation.within) && "border-bad/70")}
                />
                <Input
                  value={expectation.description}
                  aria-label="Expectation description"
                  placeholder="optional"
                  onChange={(element) =>
                    updateExpectation(position, { description: element.target.value })
                  }
                />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Remove expectation"
                  onClick={() =>
                    update({
                      expect: event.expect.filter((_, itemIndex) => itemIndex !== position),
                    })
                  }
                >
                  <Trash2 size={11} aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}
