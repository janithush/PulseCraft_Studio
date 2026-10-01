import React from "react";

export type ReelProps = {
  script: Array<{ id: string; voText: string }>;
  audioSrc: string;
  words: Array<{ word: string; start: number; end: number }>;
  brandTokens: Record<string, string>;
};

export const ReelComposition: React.FC<ReelProps> = () => {
  return <div style={{ width: 1080, height: 1920 }}>kinetic-bold (M3 implements)</div>;
};
