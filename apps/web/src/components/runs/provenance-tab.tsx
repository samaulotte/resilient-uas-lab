"use client";

import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";

const LABELS: Record<string, string> = {
  software_version: "Software version",
  scenario_api_version: "Scenario API version",
  protocol_version: "Stream protocol version",
  scenario_hash: "Scenario content hash",
  scenario_version: "Scenario version",
  adapter: "Adapter",
  adapter_version: "Adapter version",
  target_configuration: "Target configuration",
  seed: "Seed",
  speed: "Simulation speed",
  git_commit: "Git commit",
  image_versions: "Image versions",
  runner_id: "Runner",
  environment: "Environment",
  started_at: "Started at",
  ended_at: "Ended at",
  score_profile: "Score profile",
  data_origin: "Data origin",
};

const ORDER = Object.keys(LABELS);

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "not recorded";
  if (typeof value === "string") return value || "not recorded";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.length === 0 ? "none" : value.map(renderValue).join(", ");
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return "none";
    return entries.map(([key, item]) => `${key}: ${renderValue(item)}`).join("  |  ");
  }
  return String(value);
}

/** Everything needed to reproduce the run, exactly as the platform recorded it. */
export function ProvenanceTab({ provenance }: { provenance: Record<string, unknown> }) {
  const keys = [...ORDER.filter((key) => key in provenance), ...Object.keys(provenance).filter((key) => !ORDER.includes(key))];
  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Provenance</PanelTitle>
        <span className="ml-auto text-[10px] text-dim">{keys.length} recorded fields</span>
      </PanelHeader>
      <PanelBody className="p-0">
        <Table>
          <THead>
            <tr>
              <TH className="w-[220px]">Field</TH>
              <TH>Value</TH>
            </tr>
          </THead>
          <TBody>
            {keys.map((key) => (
              <TR key={key}>
                <TD className="text-muted">{LABELS[key] ?? key}</TD>
                <TD className="mono break-all">{renderValue(provenance[key])}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </PanelBody>
    </Panel>
  );
}
