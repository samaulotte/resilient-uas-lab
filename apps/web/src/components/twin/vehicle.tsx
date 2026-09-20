"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import type { TwinFeed } from "@/components/twin/feed";

const ARM_ANGLES = [Math.PI / 4, (3 * Math.PI) / 4, (5 * Math.PI) / 4, (7 * Math.PI) / 4];
const ARM_LENGTH = 2.6;
const ROTOR_RADIUS = 1.35;

/**
 * Original primitive multirotor: body, four arms, four rotor discs and a heading fin.
 * Rotors spin while the vehicle is armed; the whole group takes its pose from telemetry.
 */
export function Vehicle({ feed, reducedMotion }: { feed: TwinFeed; reducedMotion: boolean }) {
  const group = useRef<THREE.Group>(null);
  const rotorGroup = useRef<THREE.Group>(null);
  const target = useMemo(() => new THREE.Vector3(), []);
  const initialised = useRef(false);

  const bodyMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#c3d0dc", roughness: 0.55, metalness: 0.15 }),
    [],
  );
  const armMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#6d7c8b", roughness: 0.7 }),
    [],
  );
  const rotorMaterial = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: "#4fb3e8",
        transparent: true,
        opacity: 0.45,
        side: THREE.DoubleSide,
      }),
    [],
  );
  const noseMaterial = useMemo(
    () => new THREE.MeshStandardMaterial({ color: "#e0a52a", roughness: 0.5 }),
    [],
  );

  useFrame((_, delta) => {
    const sample = feed.getSample();
    const node = group.current;
    if (!node) return;
    if (!sample) {
      node.visible = false;
      return;
    }
    node.visible = true;
    target.set(sample.position.x, sample.position.z, -sample.position.y);
    if (!initialised.current) {
      node.position.copy(target);
      initialised.current = true;
    } else {
      node.position.lerp(target, Math.min(1, delta * 10));
    }
    node.rotation.set(sample.attitude.pitch, -sample.attitude.yaw, -sample.attitude.roll, "YXZ");
    if (rotorGroup.current && sample.flight.armed && !reducedMotion) {
      rotorGroup.current.rotation.y += delta * 22;
    }
  });

  return (
    <group ref={group} scale={1}>
      <mesh material={bodyMaterial} castShadow={false}>
        <boxGeometry args={[1.8, 0.7, 2.4]} />
      </mesh>
      <mesh material={noseMaterial} position={[0, 0.1, -1.6]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[0.42, 1.1, 12]} />
      </mesh>
      <group ref={rotorGroup}>
        {ARM_ANGLES.map((angle, index) => {
          const x = Math.sin(angle) * ARM_LENGTH;
          const z = Math.cos(angle) * ARM_LENGTH;
          return (
            <group key={index}>
              <mesh
                material={armMaterial}
                position={[x / 2, 0, z / 2]}
                rotation={[0, angle, Math.PI / 2]}
              >
                <cylinderGeometry args={[0.16, 0.16, ARM_LENGTH, 8]} />
              </mesh>
              <mesh material={armMaterial} position={[x, 0.18, z]}>
                <cylinderGeometry args={[0.34, 0.34, 0.42, 10]} />
              </mesh>
              <mesh
                material={rotorMaterial}
                position={[x, 0.45, z]}
                rotation={[-Math.PI / 2, 0, 0]}
              >
                <circleGeometry args={[ROTOR_RADIUS, 24]} />
              </mesh>
            </group>
          );
        })}
      </group>
    </group>
  );
}
