"use client";

import { Download, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/feedback";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiUrl } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { ArtifactInfo } from "@reslab/api-client";

export function ArtifactsTab({
  artifacts,
  runId,
  reportAvailable,
}: {
  artifacts: readonly ArtifactInfo[];
  runId: string;
  reportAvailable: boolean;
}) {
  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Artifacts</PanelTitle>
        {reportAvailable ? (
          <Button asChild variant="outline" size="xs" className="ml-auto">
            <a href={apiUrl(`/api/v1/runs/${runId}/report.html`)} target="_blank" rel="noreferrer">
              Open HTML report
              <ExternalLink size={10} aria-hidden />
            </a>
          </Button>
        ) : null}
      </PanelHeader>
      <PanelBody className="p-0">
        {artifacts.length === 0 ? (
          <EmptyState
            title="No artifact stored"
            description="Artifacts are collected once the run finishes and the analysis completes."
          />
        ) : (
          <Table>
            <THead>
              <tr>
                <TH>Name</TH>
                <TH>Description</TH>
                <TH>Content type</TH>
                <TH className="text-right">Size</TH>
                <TH>SHA-256</TH>
                <TH className="text-right">Download</TH>
              </tr>
            </THead>
            <TBody>
              {artifacts.map((artifact) => (
                <TR key={artifact.name}>
                  <TD className="mono">{artifact.name}</TD>
                  <TD className="text-muted">{artifact.description}</TD>
                  <TD className="mono text-dim">{artifact.content_type}</TD>
                  <TD className="mono text-right">{formatBytes(artifact.size_bytes)}</TD>
                  <TD className="mono max-w-[180px] truncate text-dim" title={artifact.sha256 ?? ""}>
                    {artifact.sha256 ? artifact.sha256.slice(0, 16) : "not recorded"}
                  </TD>
                  <TD className="text-right">
                    <Button asChild variant="ghost" size="xs">
                      <a href={apiUrl(artifact.url)} target="_blank" rel="noreferrer">
                        <Download size={11} aria-hidden />
                        Open
                      </a>
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </PanelBody>
    </Panel>
  );
}
