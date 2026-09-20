import * as THREE from "three";

/**
 * Build a camera-facing text label as a canvas texture.
 *
 * Sprites keep labels readable from any angle without adding DOM nodes over the canvas
 * and without loading an external font.
 */
export function createLabelSprite(
  text: string,
  options: { color?: string; background?: string; screenHeight?: number } = {},
): THREE.Sprite {
  const color = options.color ?? "#8b9bab";
  const background = options.background ?? "rgba(7, 11, 16, 0.78)";
  const fontSize = 40;
  const padding = 12;
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  const font = `600 ${fontSize}px ui-monospace, Menlo, Consolas, monospace`;
  let textWidth = text.length * fontSize * 0.6;
  if (context) {
    context.font = font;
    textWidth = context.measureText(text).width;
  }
  canvas.width = Math.ceil(textWidth + padding * 2);
  canvas.height = fontSize + padding * 2;
  if (context) {
    context.font = font;
    context.fillStyle = background;
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = "rgba(42, 56, 73, 0.9)";
    context.lineWidth = 2;
    context.strokeRect(1, 1, canvas.width - 2, canvas.height - 2);
    context.fillStyle = color;
    context.textBaseline = "middle";
    context.textAlign = "center";
    context.fillText(text, canvas.width / 2, canvas.height / 2 + 1);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  // Size attenuation is off so a label keeps the same size on screen whatever the
  // camera distance: `scale` is then a fraction of the viewport height.
  const material = new THREE.SpriteMaterial({
    map: texture,
    depthTest: false,
    transparent: true,
    sizeAttenuation: false,
  });
  const sprite = new THREE.Sprite(material);
  const height = options.screenHeight ?? 0.03;
  sprite.scale.set((canvas.width / canvas.height) * height, height, 1);
  sprite.renderOrder = 10;
  return sprite;
}

export function disposeSprite(sprite: THREE.Sprite): void {
  sprite.material.map?.dispose();
  sprite.material.dispose();
}
