"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, Play, Save } from "lucide-react";

import { AssertionEditor } from "@/components/scenario/assertion-editor";
import { EventEditor, parametersFor } from "@/components/scenario/event-editor";
import { FaultLibrary } from "@/components/scenario/fault-library";
import { TimelineEditor } from "@/components/scenario/timeline-editor";
import { RunScenarioDialog } from "@/components/runs/run-scenario-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { errorMessage, InlineError, Notice } from "@/components/ui/feedback";
import { FormRow, Input, Label, Switch, Textarea } from "@/components/ui/field";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useDebounced } from "@/hooks/use-debounced";
import { useSaveScenario, useScenarioValidation } from "@/hooks/use-scenarios";
import { useSystemInfo } from "@/hooks/use-system";
import { ApiError } from "@/lib/api";
import { parseDuration } from "@/lib/duration";
import {
  draftToYaml,
  emptyDraft,
  parseScenarioDocument,
  ScenarioParseError,
  type AdapterName,
  type EventDraft,
  type MissionType,
  type ScenarioDraft,
} from "@/lib/scenario-document";
import { componentNameMap } from "@/lib/topology";
import { cn } from "@/lib/utils";
import type { Effect } from "@reslab/api-client";

function uniqueEventId(base: string, existing: readonly EventDraft[]): string {
  const slug = base.replace(/[._]/g, "-");
  if (!existing.some((event) => event.id === slug)) return slug;
  let index = 2;
  while (existing.some((event) => event.id === `${slug}-${index}`)) index += 1;
  return `${slug}-${index}`;
}

export function ScenarioStudio({
  initialDraft,
  editingName,
  source,
}: {
  initialDraft?: ScenarioDraft;
  editingName?: string;
  source?: string;
}) {
  const router = useRouter();
  const system = useSystemInfo();
  const save = useSaveScenario();

  const [draft, setDraft] = useState<ScenarioDraft>(() => initialDraft ?? emptyDraft());
  const [yamlMode, setYamlMode] = useState(false);
  const [rawYaml, setRawYaml] = useState<string>(() =>
    draftToYaml(initialDraft ?? emptyDraft()),
  );
  const [yamlError, setYamlError] = useState<string | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const catalog = useMemo(() => system.data?.catalog ?? [], [system.data]);
  const effects = useMemo(() => system.data?.effects ?? [], [system.data]);
  const adapters = system.data?.adapters ?? [];
  const names = useMemo(() => componentNameMap(system.data?.topology), [system.data]);

  const document = yamlMode ? rawYaml : draftToYaml(draft);
  const debouncedDocument = useDebounced(document, 600);
  const validation = useScenarioValidation(debouncedDocument, true);

  const timeoutSeconds = parseDuration(draft.timeout) ?? 180;

  const patch = (next: Partial<ScenarioDraft>) => {
    setDraft((current) => {
      const updated = { ...current, ...next };
      if (!yamlMode) setRawYaml(draftToYaml(updated));
      return updated;
    });
    setSaved(null);
  };

  const setEvents = (events: EventDraft[]) => patch({ events });

  const appendInjection = (subsystem: string, effect: Effect) => {
    const descriptor = effects.find((item) => item.effect === effect);
    const last = draft.events.reduce(
      (max, event) => Math.max(max, parseDuration(event.at) ?? 0),
      0,
    );
    const at = Math.min(Math.max(last + 15, 15), Math.max(10, timeoutSeconds - 10));
    const event: EventDraft = {
      id: uniqueEventId(`${subsystem.split(".")[1] ?? subsystem}-${effect}`, draft.events),
      at: `${Math.round(at)}s`,
      subsystem,
      effect,
      duration: descriptor?.duration_required ? "20s" : "",
      parameters: parametersFor(descriptor),
      expect: [],
      description: "",
    };
    setEvents([...draft.events, event]);
    setSelectedEventId(event.id);
  };

  const toggleYamlMode = (enabled: boolean) => {
    if (enabled) {
      setRawYaml(draftToYaml(draft));
      setYamlError(null);
      setYamlMode(true);
      return;
    }
    try {
      const parsed = parseScenarioDocument(rawYaml);
      setDraft(parsed);
      setYamlError(null);
      setYamlMode(false);
    } catch (error) {
      setYamlError(
        error instanceof ScenarioParseError
          ? error.message
          : "The document could not be parsed back into the form.",
      );
    }
  };

  const onRawYamlChange = (value: string) => {
    setRawYaml(value);
    setSaved(null);
    try {
      setDraft(parseScenarioDocument(value));
      setYamlError(null);
    } catch (error) {
      setYamlError(error instanceof ScenarioParseError ? error.message : "invalid YAML");
    }
  };

  const conflict = save.error instanceof ApiError && save.error.status === 409;

  const persist = (overwrite: boolean) => {
    save.mutate(
      { document, overwrite },
      {
        onSuccess: (detail) => {
          setSaved(detail.name);
          if (!editingName || editingName !== detail.name) {
            router.push(`/scenarios/${detail.name}`);
          }
        },
      },
    );
  };

  const issues = validation.data?.issues ?? [];
  const warnings = validation.data?.warnings ?? [];
  const valid = validation.data?.valid ?? false;

  return (
    <div className="flex flex-col gap-2.5 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[13px] font-semibold tracking-[0.04em]">
          {editingName ? `Scenario studio: ${editingName}` : "Scenario studio"}
        </h1>
        {source ? (
          <Badge tone="dim" size="xs" title="Where this scenario is stored">
            {source}
          </Badge>
        ) : null}
        {validation.isFetching ? (
          <Badge tone="info" size="xs">
            VALIDATING
          </Badge>
        ) : validation.isError ? (
          <Badge tone="dim" size="xs">
            VALIDATION UNAVAILABLE
          </Badge>
        ) : validation.data ? (
          <Badge tone={valid ? "ok" : "bad"} size="xs">
            {valid ? "VALID" : `${issues.length} ISSUE${issues.length === 1 ? "" : "S"}`}
          </Badge>
        ) : null}
        {warnings.length > 0 ? (
          <Badge tone="warn" size="xs">
            {warnings.length} WARNING{warnings.length === 1 ? "" : "S"}
          </Badge>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-1.5">
            <span className="panel-title text-[9px]">YAML mode</span>
            <Switch
              checked={yamlMode}
              onCheckedChange={toggleYamlMode}
              aria-label="Edit the raw YAML document"
            />
          </label>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void validation.refetch()}
            disabled={validation.isFetching}
          >
            Validate
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={() => persist(Boolean(editingName))}
            disabled={save.isPending || !valid}
            title={valid ? "Store this document in the library" : "Fix the validation issues first"}
          >
            <Save size={11} aria-hidden />
            {save.isPending ? "Saving" : "Save to library"}
          </Button>
          <RunScenarioDialog
            trigger={
              <Button variant="primary" size="sm" disabled={!valid}>
                <Play size={11} aria-hidden />
                Run
              </Button>
            }
            document={document}
            adapters={adapters}
            defaultAdapter={draft.adapter}
            defaultSeed={draft.seed}
            title="Run the edited scenario"
          />
        </div>
      </div>

      {conflict ? (
        <div className="flex items-center gap-3 rounded-sm border border-warn/50 bg-warn-soft px-2.5 py-1.5">
          <AlertTriangle size={13} className="text-warn" aria-hidden />
          <span className="text-[11.5px] text-warn">
            A scenario named {draft.name} already exists in the library.
          </span>
          <Button variant="outline" size="xs" onClick={() => persist(true)}>
            Overwrite it
          </Button>
        </div>
      ) : save.isError ? (
        <InlineError message={errorMessage(save.error)} />
      ) : null}
      {saved ? <Notice tone="ok">Saved {saved} to the library.</Notice> : null}
      {yamlError ? <InlineError message={`YAML: ${yamlError}`} /> : null}

      <div className="grid grid-cols-[250px_minmax(420px,1fr)_400px] gap-2">
        <Panel className="h-[calc(100vh-190px)]">
          <PanelHeader>
            <PanelTitle>Fault library</PanelTitle>
          </PanelHeader>
          <PanelBody className="min-h-0 p-2">
            <FaultLibrary catalog={catalog} onPick={appendInjection} />
          </PanelBody>
        </Panel>

        <Panel className="h-[calc(100vh-190px)]">
          <PanelHeader>
            <PanelTitle>Composer</PanelTitle>
            <span className="ml-auto text-[10px] text-dim">
              {draft.events.length} events, {draft.assertions.length} assertions
            </span>
          </PanelHeader>
          <PanelBody className="flex min-h-0 flex-col gap-3 overflow-y-auto p-3">
            <section className="flex flex-col gap-2">
              <h3 className="panel-title">Metadata</h3>
              <div className="grid grid-cols-3 gap-2">
                <FormRow label="Name" hint="Lowercase letters, digits and dashes">
                  <Input
                    value={draft.name}
                    onChange={(element) => patch({ name: element.target.value })}
                    aria-label="Scenario name"
                    placeholder="my-scenario"
                    className={cn(
                      draft.name && !/^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/.test(draft.name)
                        ? "border-bad/70"
                        : undefined,
                    )}
                  />
                </FormRow>
                <FormRow label="Version">
                  <Input
                    value={draft.version}
                    onChange={(element) => patch({ version: element.target.value })}
                    aria-label="Scenario version"
                  />
                </FormRow>
                <FormRow label="Tags" hint="Comma separated">
                  <Input
                    value={draft.tags.join(", ")}
                    aria-label="Tags"
                    onChange={(element) =>
                      patch({
                        tags: element.target.value
                          .split(",")
                          .map((tag) => tag.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </FormRow>
              </div>
              <FormRow label="Description">
                <Textarea
                  rows={2}
                  value={draft.description}
                  aria-label="Scenario description"
                  onChange={(element) => patch({ description: element.target.value })}
                  placeholder="What this scenario validates"
                />
              </FormRow>
            </section>

            <section className="flex flex-col gap-2">
              <h3 className="panel-title">Target, mission and simulation</h3>
              <div className="grid grid-cols-4 gap-2">
                <FormRow label="Adapter">
                  <Select
                    value={draft.adapter}
                    onValueChange={(value) => patch({ adapter: value as AdapterName })}
                  >
                    <SelectTrigger aria-label="Adapter">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(["mock", "px4-gazebo", "replay"] as const).map((name) => (
                        <SelectItem key={name} value={name}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormRow>
                <FormRow label="Vehicle">
                  <Input
                    value={draft.vehicle}
                    aria-label="Vehicle"
                    onChange={(element) => patch({ vehicle: element.target.value })}
                  />
                </FormRow>
                <FormRow label="Mission type">
                  <Select
                    value={draft.missionType}
                    onValueChange={(value) => patch({ missionType: value as MissionType })}
                  >
                    <SelectTrigger aria-label="Mission type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(["waypoint", "hover", "survey"] as const).map((type) => (
                        <SelectItem key={type} value={type}>
                          {type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormRow>
                <FormRow label="Timeout" hint="Between 10s and 1h">
                  <Input
                    value={draft.timeout}
                    aria-label="Mission timeout"
                    onChange={(element) => patch({ timeout: element.target.value })}
                  />
                </FormRow>
                <FormRow label="Altitude (m)">
                  <Input
                    type="number"
                    value={draft.altitude}
                    aria-label="Mission altitude"
                    onChange={(element) => patch({ altitude: Number(element.target.value) })}
                  />
                </FormRow>
                <FormRow label="Cruise speed (m/s)">
                  <Input
                    type="number"
                    step="0.5"
                    value={draft.cruiseSpeed}
                    aria-label="Cruise speed"
                    onChange={(element) => patch({ cruiseSpeed: Number(element.target.value) })}
                  />
                </FormRow>
                <FormRow label="Seed">
                  <Input
                    type="number"
                    value={draft.seed}
                    aria-label="Simulation seed"
                    onChange={(element) => patch({ seed: Number(element.target.value) })}
                  />
                </FormRow>
                <FormRow label="Simulation speed">
                  <Input
                    type="number"
                    step="0.5"
                    value={draft.speed}
                    aria-label="Simulation speed"
                    onChange={(element) => patch({ speed: Number(element.target.value) })}
                  />
                </FormRow>
              </div>
            </section>

            <section className="flex flex-col gap-2">
              <h3 className="panel-title">Declared recovery policy</h3>
              <p className="text-[10.5px] text-dim">
                What the target is expected to do. The platform verifies these behaviours, it never
                commands them.
              </p>
              <div className="grid grid-cols-5 gap-2">
                <FormRow label="GNSS loss">
                  <Select
                    value={draft.recovery.gnssLoss}
                    onValueChange={(value) =>
                      patch({
                        recovery: {
                          ...draft.recovery,
                          gnssLoss: value as ScenarioDraft["recovery"]["gnssLoss"],
                        },
                      })
                    }
                  >
                    <SelectTrigger aria-label="GNSS loss policy">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(["dead_reckoning", "hold", "land"] as const).map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormRow>
                <FormRow label="Datalink loss">
                  <Select
                    value={draft.recovery.datalinkLoss}
                    onValueChange={(value) =>
                      patch({
                        recovery: {
                          ...draft.recovery,
                          datalinkLoss: value as ScenarioDraft["recovery"]["datalinkLoss"],
                        },
                      })
                    }
                  >
                    <SelectTrigger aria-label="Datalink loss policy">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(["continue", "hold", "rtl"] as const).map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormRow>
                <FormRow label="Compute loss">
                  <Select
                    value={draft.recovery.computeLoss}
                    onValueChange={(value) =>
                      patch({
                        recovery: {
                          ...draft.recovery,
                          computeLoss: value as ScenarioDraft["recovery"]["computeLoss"],
                        },
                      })
                    }
                  >
                    <SelectTrigger aria-label="Compute loss policy">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(["hold", "land", "rtl"] as const).map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormRow>
                <FormRow label="Hold timeout">
                  <Input
                    value={draft.recovery.holdTimeout}
                    aria-label="Hold timeout"
                    onChange={(element) =>
                      patch({ recovery: { ...draft.recovery, holdTimeout: element.target.value } })
                    }
                  />
                </FormRow>
                <FormRow label="Max dead reckoning">
                  <Input
                    value={draft.recovery.maxDeadReckoning}
                    aria-label="Maximum dead reckoning"
                    onChange={(element) =>
                      patch({
                        recovery: { ...draft.recovery, maxDeadReckoning: element.target.value },
                      })
                    }
                  />
                </FormRow>
              </div>
            </section>

            <section className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <h3 className="panel-title">Event timeline</h3>
                <span className="text-[10px] text-dim">
                  Mission timeout {draft.timeout}. Click a marker to select an event.
                </span>
              </div>
              <div className="rounded-sm border border-border bg-panel-2 px-1 py-1">
                <TimelineEditor
                  events={draft.events}
                  timeoutSeconds={timeoutSeconds}
                  selectedId={selectedEventId}
                  onSelect={setSelectedEventId}
                  names={names}
                />
              </div>
              {draft.preserved.profile ? (
                <Notice tone="info">
                  This scenario carries a consequence profile. It is preserved as written and
                  expanded into injections at load time.
                </Notice>
              ) : null}
            </section>

            <section className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Label>Events</Label>
                <span className="text-[10px] text-dim">
                  Pick an effect in the fault library to append one
                </span>
              </div>
              {draft.events.length === 0 ? (
                <p className="rounded-sm border border-dashed border-border-strong px-3 py-4 text-center text-[11.5px] text-muted">
                  No event yet. A scenario needs at least one event or a consequence profile.
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {draft.events.map((event, index) => (
                    <EventEditor
                      key={`${event.id}-${index}`}
                      event={event}
                      index={index}
                      total={draft.events.length}
                      catalog={catalog}
                      effects={effects}
                      selected={event.id === selectedEventId}
                      onSelect={() => setSelectedEventId(event.id)}
                      onChange={(next) =>
                        setEvents(
                          draft.events.map((item, position) => (position === index ? next : item)),
                        )
                      }
                      onRemove={() =>
                        setEvents(draft.events.filter((_, position) => position !== index))
                      }
                      onMove={(direction) => {
                        const target = index + direction;
                        if (target < 0 || target >= draft.events.length) return;
                        const next = [...draft.events];
                        const moved = next[index];
                        const swapped = next[target];
                        if (!moved || !swapped) return;
                        next[index] = swapped;
                        next[target] = moved;
                        setEvents(next);
                      }}
                    />
                  ))}
                </ul>
              )}
            </section>

            <section>
              <AssertionEditor
                assertions={draft.assertions}
                onChange={(assertions) => patch({ assertions })}
              />
            </section>
          </PanelBody>
        </Panel>

        <div className="flex h-[calc(100vh-190px)] min-h-0 flex-col gap-2">
          <Panel className="min-h-0 flex-1">
            <PanelHeader>
              <PanelTitle>{yamlMode ? "YAML document (editable)" : "YAML document"}</PanelTitle>
              <Button
                variant="ghost"
                size="xs"
                className="ml-auto"
                onClick={() => void navigator.clipboard?.writeText(document)}
              >
                <Copy size={10} aria-hidden />
                Copy
              </Button>
            </PanelHeader>
            <PanelBody className="min-h-0 p-0">
              {yamlMode ? (
                <Textarea
                  value={rawYaml}
                  onChange={(element) => onRawYamlChange(element.target.value)}
                  aria-label="Scenario YAML document"
                  spellCheck={false}
                  className="mono h-full resize-none rounded-none border-0 bg-transparent text-[11.5px]"
                />
              ) : (
                <pre className="mono h-full overflow-auto p-3 text-[11.5px] leading-relaxed text-foreground">
                  {document}
                </pre>
              )}
            </PanelBody>
          </Panel>

          <Panel className="h-[220px] shrink-0">
            <PanelHeader>
              <PanelTitle>Validation</PanelTitle>
              {validation.data && valid && warnings.length === 0 ? (
                <CheckCircle2 size={12} className="ml-auto text-ok" aria-hidden />
              ) : null}
            </PanelHeader>
            <PanelBody className="overflow-y-auto p-2">
              {validation.isError ? (
                <InlineError message={errorMessage(validation.error)} />
              ) : !validation.data ? (
                <p className="text-[11.5px] text-muted">
                  The document is validated by the platform as you type.
                </p>
              ) : (
                <div className="flex flex-col gap-2">
                  {issues.length === 0 && warnings.length === 0 ? (
                    <p className="text-[11.5px] text-ok">
                      The document is valid against the scenario schema and the fault catalog.
                    </p>
                  ) : null}
                  {issues.length > 0 ? (
                    <ul className="flex flex-col gap-1">
                      {issues.map((issue, index) => (
                        <li
                          key={`${issue.path}-${index}`}
                          className="rounded-sm border border-bad/40 bg-bad-soft px-2 py-1"
                        >
                          <span className="mono block text-[10.5px] text-bad">{issue.path}</span>
                          <span className="block text-[11.5px] text-foreground">
                            {issue.message}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {warnings.length > 0 ? (
                    <ul className="flex flex-col gap-1">
                      {warnings.map((warning, index) => (
                        <li
                          key={`${warning.path}-${index}`}
                          className="rounded-sm border border-warn/40 bg-warn-soft px-2 py-1"
                        >
                          <span className="mono block text-[10.5px] text-warn">{warning.path}</span>
                          <span className="block text-[11.5px] text-foreground">
                            {warning.message}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {validation.data.content_hash ? (
                    <p className="mono text-[10px] text-dim">
                      content hash {validation.data.content_hash.replace("sha256:", "").slice(0, 16)}
                    </p>
                  ) : null}
                </div>
              )}
            </PanelBody>
          </Panel>
        </div>
      </div>
    </div>
  );
}
