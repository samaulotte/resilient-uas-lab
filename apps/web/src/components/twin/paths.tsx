"use client";

import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { toSceneVector, type TwinFeed } from "@/components/twin/feed";
import { SceneLabel } from "@/components/twin/label";
import type { PlannedPath } from "@reslab/api-client";

const MAX_TRAIL_POINTS = 6000;
/** Minimum spacing between recorded path points, in metres. */
const MIN_STEP = 0.4;

/** Planned mission: dashed polyline with numbered waypoint markers. */
export function PlannedRoute({ path }: { path: PlannedPath | null }) {
  const points = useMemo<[number, number, number][]>(
    () => (path?.waypoints ?? []).map((waypoint) => toSceneVector(waypoint)),
    [path],
  );
  if (points.length < 2) return null;
  return (
    <group>
      <Line
        points={points}
        color="#4a6b86"
        lineWidth={1.4}
        dashed
        dashSize={3}
        gapSize={2.4}
        transparent
        opacity={0.85}
      />
      {points.map((point, index) => (
        <group key={index} position={point}>
          <mesh>
            <sphereGeometry args={[0.9, 12, 12]} />
            <meshStandardMaterial color="#6f93ad" emissive="#16222c" />
          </mesh>
          <SceneLabel
            text={`WP${index}`}
            position={[0, 3.2, 0]}
            color="#9fb3c4"
            screenHeight={0.034}
          />
        </group>
      ))}
    </group>
  );
}

/** Safe zone ring drawn flat on the ground at the declared return point. */
export function SafeZone({ path }: { path: PlannedPath | null }) {
  if (!path?.safe_zone) return null;
  const { x, y } = path.safe_zone;
  const radius = path.safe_zone_radius;
  return (
    <mesh position={[x, 0.06, -y]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[Math.max(0.5, radius - 0.45), radius, 64]} />
      <meshBasicMaterial color="#4fb3e8" transparent opacity={0.4} side={THREE.DoubleSide} />
    </mesh>
  );
}

/**
 * Flown path, appended incrementally.
 *
 * The geometry is preallocated once and only the new points are written each frame, so
 * a long run never rebuilds a buffer of thousands of vertices.
 */
export function FlownPath({ feed }: { feed: TwinFeed }) {
  const geometry = useMemo(() => {
    const buffer = new THREE.BufferGeometry();
    buffer.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(MAX_TRAIL_POINTS * 3), 3),
    );
    buffer.setDrawRange(0, 0);
    return buffer;
  }, []);
  const material = useMemo(
    () => new THREE.LineBasicMaterial({ color: "#7cc6f0", transparent: true, opacity: 0.95 }),
    [],
  );
  const line = useMemo(() => new THREE.Line(geometry, material), [geometry, material]);
  const count = useRef(0);
  const lastTime = useRef(-Infinity);
  const lastPoint = useRef(new THREE.Vector3());
  const scratch = useRef(new THREE.Vector3());
  const generation = useRef(-1);

  useEffect(
    () => () => {
      geometry.dispose();
      material.dispose();
    },
    [geometry, material],
  );

  useFrame(() => {
    const currentGeneration = feed.getGeneration();
    if (currentGeneration !== generation.current) {
      generation.current = currentGeneration;
      count.current = 0;
      lastTime.current = -Infinity;
      geometry.setDrawRange(0, 0);
    }
    const trail = feed.getTrail();
    if (trail.length === 0) return;
    const attribute = geometry.getAttribute("position") as THREE.BufferAttribute;
    const positions = attribute.array as Float32Array;
    let appended = false;
    for (const sample of trail) {
      if (sample.t <= lastTime.current) continue;
      lastTime.current = sample.t;
      const x = sample.position.x;
      const yUp = sample.position.z;
      const z = -sample.position.y;
      scratch.current.set(x, yUp, z);
      if (count.current > 0 && lastPoint.current.distanceTo(scratch.current) < MIN_STEP) {
        continue;
      }
      if (count.current >= MAX_TRAIL_POINTS) break;
      const offset = count.current * 3;
      positions[offset] = x;
      positions[offset + 1] = yUp;
      positions[offset + 2] = z;
      lastPoint.current.set(x, yUp, z);
      count.current += 1;
      appended = true;
    }
    if (appended) {
      attribute.needsUpdate = true;
      geometry.setDrawRange(0, count.current);
      geometry.computeBoundingSphere();
    }
  });

  return <primitive object={line} />;
}
