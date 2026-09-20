"use client";

import { useMemo, useRef } from "react";

import { useElementWidth } from "@/hooks/use-element-size";
import { DOMAIN_LABEL, DOMAIN_ORDER } from "@/lib/states";
import type { Domain, SystemTopology } from "@reslab/api-client";

const LABEL_WIDTH = 132;
const BAND_HEIGHT = 86;
const NODE_HEIGHT = 30;
const NODE_MAX_WIDTH = 150;
const TOP_PAD = 14;

const ZONE_COLOR: Record<string, string> = {
  external: "#8b9bab",
  mission: "#4fb3e8",
  flight_critical: "#e0a52a",
};

interface Placed {
  id: string;
  name: string;
  x: number;
  y: number;
  width: number;
  zone: string;
  critical: boolean;
}

/**
 * Dependency graph of the system: domains as bands, components as nodes, dependencies as
 * edges, trust boundaries as dashed lines labelled with their enforcement point.
 */
export function TopologyGraph({ topology }: { topology: SystemTopology }) {
  const container = useRef<HTMLDivElement>(null);
  const width = useElementWidth(container);

  const { nodes, height, boundaryRows } = useMemo(() => {
    const byDomain = new Map<Domain, typeof topology.components>();
    for (const component of topology.components) {
      const list = byDomain.get(component.domain);
      if (list) list.push(component);
      else byDomain.set(component.domain, [component]);
    }
    const bands = DOMAIN_ORDER.filter((domain) => byDomain.has(domain));
    const plot = Math.max(240, width - LABEL_WIDTH - 16);
    const placed: Placed[] = [];
    bands.forEach((domain, bandIndex) => {
      const components = byDomain.get(domain) ?? [];
      const slot = plot / components.length;
      const nodeWidth = Math.min(NODE_MAX_WIDTH, Math.max(84, slot - 14));
      components.forEach((component, index) => {
        placed.push({
          id: component.id,
          name: component.name,
          x: LABEL_WIDTH + slot * index + (slot - nodeWidth) / 2,
          y: TOP_PAD + bandIndex * BAND_HEIGHT + (BAND_HEIGHT - NODE_HEIGHT) / 2,
          width: nodeWidth,
          zone: component.trust_zone,
          critical: component.critical,
        });
      });
    });
    const rows = new Map<string, number>();
    for (const boundary of topology.trust_boundaries) {
      const index = bands.findIndex((domain) =>
        (byDomain.get(domain) ?? []).some(
          (component) => component.trust_zone === boundary.downstream_zone,
        ),
      );
      if (index > 0) rows.set(boundary.id, index);
    }
    return {
      nodes: placed,
      bands,
      height: TOP_PAD * 2 + bands.length * BAND_HEIGHT,
      boundaryRows: rows,
    };
  }, [topology, width]);

  const byId = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const bands = DOMAIN_ORDER.filter((domain) =>
    topology.components.some((component) => component.domain === domain),
  );

  return (
    <div ref={container} className="w-full">
      {width > 0 ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label="System topology: components grouped by domain with their dependencies"
        >
          {bands.map((domain, index) => (
            <g key={domain}>
              <rect
                x={0}
                y={TOP_PAD + index * BAND_HEIGHT}
                width={width}
                height={BAND_HEIGHT}
                fill={index % 2 === 0 ? "#0b1118" : "#0e151d"}
              />
              <text
                x={8}
                y={TOP_PAD + index * BAND_HEIGHT + BAND_HEIGHT / 2 + 4}
                fontSize={10.5}
                fill="#8b9bab"
                className="panel-title"
              >
                {DOMAIN_LABEL[domain].toUpperCase()}
              </text>
            </g>
          ))}

          {topology.dependencies.map((dependency, index) => {
            const from = byId.get(dependency.provider);
            const to = byId.get(dependency.dependent);
            if (!from || !to) return null;
            const x1 = from.x + from.width / 2;
            const y1 = from.y + NODE_HEIGHT / 2;
            const x2 = to.x + to.width / 2;
            const y2 = to.y + NODE_HEIGHT / 2;
            const midY = (y1 + y2) / 2;
            return (
              <path
                key={`${dependency.provider}-${dependency.dependent}-${index}`}
                d={`M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`}
                fill="none"
                stroke={dependency.crosses_trust_boundary ? "#e0a52a" : "#2a3849"}
                strokeWidth={dependency.crosses_trust_boundary ? 1.4 : 1}
                strokeDasharray={dependency.crosses_trust_boundary ? "4 3" : undefined}
                opacity={dependency.crosses_trust_boundary ? 0.95 : 0.7}
              >
                <title>{`${dependency.provider} ${dependency.relation} ${dependency.dependent}`}</title>
              </path>
            );
          })}

          {topology.trust_boundaries.map((boundary) => {
            const index = boundaryRows.get(boundary.id);
            if (index === undefined) return null;
            const y = TOP_PAD + index * BAND_HEIGHT;
            return (
              <g key={boundary.id}>
                <line
                  x1={4}
                  x2={width - 4}
                  y1={y}
                  y2={y}
                  stroke="#4fb3e8"
                  strokeWidth={1.2}
                  strokeDasharray="7 5"
                />
                <text x={LABEL_WIDTH} y={y - 4} fontSize={9.5} className="mono" fill="#4fb3e8">
                  {boundary.name}
                  {boundary.enforcement_point
                    ? `  |  enforced at ${boundary.enforcement_point}`
                    : ""}
                </text>
              </g>
            );
          })}

          {nodes.map((node) => (
            <g key={node.id}>
              <rect
                x={node.x}
                y={node.y}
                width={node.width}
                height={NODE_HEIGHT}
                rx={3}
                fill="#121b25"
                stroke={ZONE_COLOR[node.zone] ?? "#2a3849"}
                strokeWidth={node.critical ? 1.6 : 1}
              />
              <text
                x={node.x + node.width / 2}
                y={node.y + 13}
                fontSize={10}
                fill="#e6edf3"
                textAnchor="middle"
              >
                {node.name.length > 20 ? `${node.name.slice(0, 19)}.` : node.name}
              </text>
              <text
                x={node.x + node.width / 2}
                y={node.y + 24}
                fontSize={8.5}
                className="mono"
                fill="#5d6b7a"
                textAnchor="middle"
              >
                {node.id}
              </text>
              <title>{`${node.name} (${node.id}), trust zone ${node.zone}${node.critical ? ", flight critical" : ""}`}</title>
            </g>
          ))}
        </svg>
      ) : (
        <div className="h-[560px]" />
      )}
      <ul className="mt-2 flex flex-wrap items-center gap-4 text-[10.5px] text-dim">
        {Object.entries(ZONE_COLOR).map(([zone, color]) => (
          <li key={zone} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-4 rounded-sm border"
              style={{ borderColor: color }}
            />
            trust zone {zone}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-px w-5 border-t border-dashed border-warn" />
          dependency crossing a trust boundary
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-px w-5 border-t border-dashed border-info" />
          trust boundary
        </li>
      </ul>
    </div>
  );
}
