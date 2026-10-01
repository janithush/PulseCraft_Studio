import React from "react";
import { AbsoluteFill, Img, interpolate, useCurrentFrame } from "remotion";

export type DocuProps = {
  script: Array<{ id: string; voText: string }>;
  audioSrc?: string;
  words: Array<{ word: string; start: number; end: number }>;
  brandTokens: Record<string, string>;
  width?: number;
  height?: number;
  brollSrc?: string;
};

export const ReelComposition: React.FC<DocuProps> = ({
  words,
  brandTokens,
  width = 1080,
  height = 1920,
  brollSrc,
}) => {
  const frame = useCurrentFrame();
  const fps = 30;
  const zoom = interpolate(frame, [0, 900], [1, 1.12], { extrapolateRight: "clamp" });
  const line = words
    .filter((w) => w.start * fps <= frame)
    .slice(-6)
    .map((w) => w.word)
    .join(" ");
  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0a", width, height }}>
      {brollSrc ? (
        <Img src={brollSrc} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` }} />
      ) : null}
      <AbsoluteFill
        style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.55), rgba(0,0,0,0.15) 40%, rgba(0,0,0,0.7))" }}
      />
      <div
        style={{
          position: "absolute",
          bottom: height * 0.18,
          padding: "0 90px",
          fontFamily: brandTokens.serif ?? "Georgia, serif",
          fontSize: 64,
          lineHeight: 1.25,
          color: "#f5f1e8",
          textShadow: "0 2px 12px rgba(0,0,0,0.8)",
        }}
      >
        {line}
      </div>
    </AbsoluteFill>
  );
};
