"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FormRow, Input } from "@/components/ui/field";
import { errorMessage, InlineError, Notice } from "@/components/ui/feedback";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCreateRun } from "@/hooks/use-runs";
import type { AdapterInfo } from "@reslab/api-client";

const SPEEDS = ["1", "2", "5", "10", "25", "50"] as const;

export function RunScenarioDialog({
  trigger,
  scenarioName,
  document,
  adapters,
  defaultAdapter,
  defaultSpeed = "1",
  defaultSeed,
  title = "Run scenario",
}: {
  trigger: React.ReactNode;
  scenarioName?: string;
  document?: string;
  adapters: readonly AdapterInfo[];
  defaultAdapter: string;
  defaultSpeed?: string;
  defaultSeed?: number;
  title?: string;
}) {
  const router = useRouter();
  const create = useCreateRun();
  const [open, setOpen] = useState(false);
  const [adapter, setAdapter] = useState(defaultAdapter);
  const [speed, setSpeed] = useState<string>(defaultSpeed);
  const [seed, setSeed] = useState<string>(defaultSeed !== undefined ? String(defaultSeed) : "");
  const [label, setLabel] = useState("");

  const runnable = adapters.filter((entry) => entry.online);
  const selectedOffline = !runnable.some((entry) => entry.name === adapter);

  const submit = () => {
    const seedValue = seed.trim() === "" ? null : Number(seed);
    create.mutate(
      {
        ...(scenarioName ? { scenario_name: scenarioName } : {}),
        ...(document ? { document } : {}),
        adapter: adapter as "mock" | "px4-gazebo" | "replay",
        speed: Number(speed),
        ...(seedValue !== null && Number.isFinite(seedValue) ? { seed: seedValue } : {}),
        label: label.trim(),
      },
      {
        onSuccess: (run) => {
          setOpen(false);
          router.push(`/mission-control?run=${run.id}`);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent aria-describedby="run-dialog-description">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription id="run-dialog-description">
            {scenarioName
              ? `Queue '${scenarioName}' on a runner and open Mission Control.`
              : "Queue the edited document on a runner and open Mission Control."}
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <div className="grid grid-cols-2 gap-3">
            <FormRow label="Adapter" hint="Only adapters with an online runner can execute a run.">
              <Select value={adapter} onValueChange={setAdapter}>
                <SelectTrigger aria-label="Adapter">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {adapters.map((entry) => (
                    <SelectItem key={entry.name} value={entry.name} disabled={!entry.online}>
                      {entry.display_name}
                      {entry.online ? "" : " (offline)"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormRow>
            <FormRow label="Simulation speed" hint="Higher speeds compress the same mission time.">
              <Select value={speed} onValueChange={setSpeed}>
                <SelectTrigger aria-label="Simulation speed">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SPEEDS.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}x
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </FormRow>
            <FormRow label="Seed" htmlFor="run-seed" hint="Leave empty to use the scenario seed.">
              <Input
                id="run-seed"
                inputMode="numeric"
                value={seed}
                onChange={(event) => setSeed(event.target.value)}
                placeholder="scenario default"
              />
            </FormRow>
            <FormRow label="Label" htmlFor="run-label" hint="Free text shown in the run list.">
              <Input
                id="run-label"
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder="optional"
              />
            </FormRow>
          </div>
          {selectedOffline ? (
            <Notice tone="warn">
              No runner currently advertises this adapter. The run will stay queued until one comes
              online.
            </Notice>
          ) : null}
          {create.isError ? <InlineError message={errorMessage(create.error)} /> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} disabled={create.isPending}>
            {create.isPending ? "Queueing" : "Run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
