export function durationFromWords(
  words: Array<{ start: number; end: number }>,
  fps: number,
  fallbackFrames = 900,
  minFrames = 90,
): number {
  if (!words.length || fps <= 0) {
    return fallbackFrames;
  }
  const last = words[words.length - 1].end;
  if (!Number.isFinite(last) || last <= 0) {
    return fallbackFrames;
  }
  return Math.max(minFrames, Math.ceil(last * fps));
}
