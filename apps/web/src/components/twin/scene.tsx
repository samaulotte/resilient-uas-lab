"use client";

import { Grid, Line, OrbitControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import type { TwinFeed } from "@/components/twin/feed";
import { SceneLabel } from "@/components/twin/label";
import { FlownPath, PlannedRoute, SafeZone } from "@/components/twin/paths";
import { Vehicle } from "@/components/twin/vehicle";
import type { CameraMode } from "@/stores/settings";
import type { PlannedPath } from "@reslab/api-client";

type OrbitControlsHandle = React.ComponentRef<typeof OrbitControls>;

/** Heading vector in the scene frame: yaw 0 points north (-z), clockwise positive. */
function headingVector(yaw: number, out: THREE.Vector3): THREE.Vector3 {
  return out.set(Math.sin(yaw), 0, -Math.cos(yaw));
}

function pathExtent(path: PlannedPath | null): { center: THREE.Vector3; radius: number } {
  const center = new THREE.Vector3();
  const waypoints = path?.waypoints ?? [];
  if (waypoints.length === 0) return { center, radius: 120 };
  let minX = Infinity;
  let maxX = -Infinity;
  let minZ = Infinity;
  let maxZ = -Infinity;
  for (const waypoint of waypoints) {
    minX = Math.min(minX, waypoint.x);
    maxX = Math.max(maxX, waypoint.x);
    minZ = Math.min(minZ, -waypoint.y);
    maxZ = Math.max(maxZ, -waypoint.y);
  }
  center.set((minX + maxX) / 2, 0, (minZ + maxZ) / 2);
  const radius = Math.max(60, Math.max(maxX - minX, maxZ - minZ) * 0.72);
  return { center, radius };
}

function CameraRig({
  feed,
  mode,
  plannedPath,
}: {
  feed: TwinFeed;
  mode: CameraMode;
  plannedPath: PlannedPath | null;
}) {
  const { camera } = useThree();
  const controls = useRef<OrbitControlsHandle | null>(null);
  const desired = useMemo(() => new THREE.Vector3(), []);
  const focus = useMemo(() => new THREE.Vector3(), []);
  const heading = useMemo(() => new THREE.Vector3(), []);
  const vehicle = useMemo(() => new THREE.Vector3(), []);
  const extent = useMemo(() => pathExtent(plannedPath), [plannedPath]);

  useFrame((_, delta) => {
    const sample = feed.getSample();
    if (sample) {
      vehicle.set(sample.position.x, sample.position.z, -sample.position.y);
      headingVector(sample.attitude.yaw, heading);
    } else {
      vehicle.copy(extent.center);
      heading.set(0, 0, -1);
    }
    const smoothing = Math.min(1, delta * 3.4);

    if (mode === "orbit") {
      if (controls.current) {
        controls.current.target.lerp(vehicle, smoothing);
        controls.current.update();
      }
      return;
    }

    if (mode === "top") {
      desired.set(extent.center.x, extent.radius * 1.55, extent.center.z + 0.01);
      focus.copy(extent.center);
    } else if (mode === "fpv") {
      desired
        .copy(vehicle)
        .addScaledVector(heading, 2.2)
        .add(new THREE.Vector3(0, 1.1, 0));
      focus.copy(vehicle).addScaledVector(heading, 60);
    } else {
      desired
        .copy(vehicle)
        .addScaledVector(heading, -22)
        .add(new THREE.Vector3(0, 11, 0));
      focus.copy(vehicle).addScaledVector(heading, 8);
    }
    camera.position.lerp(desired, mode === "fpv" ? Math.min(1, delta * 9) : smoothing);
    camera.lookAt(focus);
  });

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enabled={mode === "orbit"}
      enableDamping
      dampingFactor={0.12}
      minDistance={8}
      maxDistance={700}
      maxPolarAngle={Math.PI / 2.05}
    />
  );
}

const COMPASS_MARKS: { label: string; position: [number, number, number] }[] = [
  { label: "N", position: [0, 6, -150] },
  { label: "E", position: [150, 6, 0] },
  { label: "S", position: [0, 6, 150] },
  { label: "W", position: [-150, 6, 0] },
];

/** Faint cardinal marks and a north axis hint on the ground plane. */
function Compass() {
  return (
    <group>
      <Line
        points={[
          [0, 0.05, 0],
          [0, 0.05, -150],
        ]}
        color="#2d4356"
        lineWidth={1.2}
      />
      <Line
        points={[
          [-150, 0.05, 0],
          [150, 0.05, 0],
        ]}
        color="#1c2a38"
        lineWidth={1}
      />
      {COMPASS_MARKS.map((mark) => (
        <SceneLabel
          key={mark.label}
          text={mark.label}
          position={mark.position}
          color="#7f8fa0"
          screenHeight={0.038}
        />
      ))}
    </group>
  );
}

export function TwinScene({
  feed,
  plannedPath,
  cameraMode,
  reducedMotion,
}: {
  feed: TwinFeed;
  plannedPath: PlannedPath | null;
  cameraMode: CameraMode;
  reducedMotion: boolean;
}) {
  return (
    <>
      <color attach="background" args={["#070b10"]} />
      <fog attach="fog" args={["#070b10", 260, 900]} />
      <hemisphereLight args={["#4c6274", "#0a1017", 1.1]} />
      <directionalLight position={[120, 180, 90]} intensity={1.15} color="#d8e6f2" />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]}>
        <planeGeometry args={[2400, 2400]} />
        <meshStandardMaterial color="#0a0f16" roughness={1} />
      </mesh>
      <Grid
        args={[700, 700]}
        position={[0, 0.02, 0]}
        cellSize={10}
        cellThickness={0.5}
        cellColor="#16202c"
        sectionSize={50}
        sectionThickness={0.9}
        sectionColor="#22344a"
        fadeDistance={640}
        fadeStrength={1.1}
      />
      <Compass />
      <PlannedRoute path={plannedPath} />
      <SafeZone path={plannedPath} />
      <FlownPath feed={feed} />
      <Vehicle feed={feed} reducedMotion={reducedMotion} />
      <CameraRig feed={feed} mode={cameraMode} plannedPath={plannedPath} />
    </>
  );
}
