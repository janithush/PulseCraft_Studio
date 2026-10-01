export function paginateWords<T>(words: T[], maxPerLine: number): T[][] {
  const perLine = Math.max(1, maxPerLine);
  const lines: T[][] = [];
  for (let i = 0; i < words.length; i += perLine) {
    lines.push(words.slice(i, i + perLine));
  }
  return lines;
}
