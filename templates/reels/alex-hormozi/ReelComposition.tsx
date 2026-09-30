import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";

export type HormoziProps = {
  script: Array<{ id: string; voText: string }>;
  audioSrc?: string;
  words: Array<{ word: string; start: number; end: number }>;
  brandTokens: Record<string, string>;
  width?: number;
  height?: number;
  highlight?: string;
};

const visibleWords = (words: HormoziProps["words"], fps: number, frame: number) =>
  words.filter((w) => w.start * fps <= frame && frame <= w.end * fps + 6).slice(-8);

export const ReelComposition: React.FC<HormoziProps> = ({
  words,
  brandTokens,
  width = 1080,
  height = 1920,
  highlight = "yellow",
}) => {
  const frame = useCurrentFrame();
  const fps = 30;
  const active = visibleWords(words, fps, frame);
  const pop = 1 + 0.12 * Math.abs(Math.sin(frame / 3));
  return (
    <AbsoluteFill style={{ backgroundColor: brandTokens.bg ?? "#000", width, height }}>
      <div style={{ position: "absolute", top: 0, height: 12, width: `${(frame % 900) / 9}%`, backgroundColor: highlight }} />
      <div style={{ padding: 80, marginTop: height * 0.3 }}>
        {active.map((w, i) => (
          <span
            key={`${w.word}-${i}`}
            style={{
              display: "inline-block",
              marginRight: 18,
              fontSize: 84,
              fontWeight: 900,
              transform: i === active.length - 1 ? `scale(${pop})` : undefined,
              color: i === active.length - 1 ? highlight : "#fff",
            }}
          >
            {w.word}
          </span>
        ))}
      </div>
      <Sequence from={0} durationInFrames={90}>
        <div style={{ position: "absolute", top: 60, width: "100%", textAlign: "center", fontSize: 40 }}>
          HOOK
        </div>
      </Sequence>
    </AbsoluteFill>
  );
};
