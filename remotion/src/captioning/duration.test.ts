import { describe, expect, it } from "vitest";
import { durationFromWords } from "./duration";

describe("durationFromWords", () => {
  it("converts the last word end to frames", () => {
    const words = [
      { start: 0, end: 0.5 },
      { start: 0.6, end: 4.0 },
    ];
    expect(durationFromWords(words, 30)).toBe(120);
  });

  it("falls back when there are no words", () => {
    expect(durationFromWords([], 30)).toBe(900);
  });

  it("enforces a minimum duration", () => {
    expect(durationFromWords([{ start: 0, end: 0.1 }], 30)).toBe(90);
  });
});
