"use client";

import { useEffect, useMemo } from "react";
import type * as THREE from "three";

import { createLabelSprite, disposeSprite } from "@/components/twin/label-sprite";

/** Camera-facing text label of constant screen size, placed in the scene. */
export function SceneLabel({
  text,
  position,
  color,
  screenHeight,
}: {
  text: string;
  position: [number, number, number];
  color?: string;
  screenHeight?: number;
}) {
  const sprite = useMemo<THREE.Sprite>(
    () => createLabelSprite(text, { color, screenHeight }),
    [text, color, screenHeight],
  );
  useEffect(() => () => disposeSprite(sprite), [sprite]);
  return <primitive object={sprite} position={position} />;
}
