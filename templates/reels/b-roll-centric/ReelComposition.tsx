import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";

export type BrollProps = {
  script: Array<{ id: string; voText: string }>;
  audioSrc?: string;
  words: Array<{ word: string; start: number; end: number }>;
  brandTokens: Record<string, string>;
  width?: number;
  height?: number;
  scenes?: Array<{ id: string; assetUrl?: string }>;
};

const currentScene = (scenes: BrollProps["scenes"], frame: number, fps: number) => {
  if (!scenes?.length) return undefined;
  const per = Math.floor(900 / scenes.length) || 900;
  return scenes[Math.min(Math.floor(frame / per), scenes.length - 1)];
};

export const ReelComposition: React.FC<BrollProps> = ({
  words,
  width = 1080,
  height = 1920,
  scenes,
}) => {
  const frame = useCurrentFrame();
  const fps = 30;
  const scene = currentScene(scenes, frame, fps);
  const subtitle = words
    .filter((w) => w.start * fps <= frame)
    .slice(-4)
    .map((w) => w.word)
    .join(" ");
  return (
    <AbsoluteFill style={{ backgroundColor: "#111", width, height }}>
      {scene?.assetUrl ? (
        <Img src={scene.assetUrl.startsWith("http") ? scene.assetUrl : staticFile(scene.assetUrl)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : null}
      <div
        style={{
          position: "absolute",
          bottom: 120,
          width: "100%",
          textAlign: "center",
          padding: "0 70px",
          fontSize: 56,
          fontWeight: 600,
          color: "#fff",
          textShadow: "0 2px 8px rgba(0,0,0,0.9)",
          background: "rgba(0,0,0,0.35)",
        }}
      >
        {subtitle}
      </div>
    </AbsoluteFill>
  );
};
