// Audio CPU of a selection of mods, from tools/build/budget.py (budget.json): extra cycles per audio block on CPU #1,
// worst case, summed over the chosen mods (dependencies included). Pure: tested in test/cpu.test.ts.

export interface Budget {
  limits: { cpu: number };
  audio: { block: number; stock: number };
  mods: Record<string, { cpu: number }>;
}

export interface AudioLoad {
  cycles: number;          // extra cycles per block
  percent: number;         // share of each audio block used by the OS and the mods (stock at rest included)
  over: boolean;           // above the budget: allowed, but the site warns
  heaviest: string[];      // the mods that cost the most, heaviest first
}

export function audioLoad(budget: Budget, names: string[]): AudioLoad {
  const cost = (n: string): number => budget.mods[n]?.cpu ?? 0;
  const cycles = names.reduce((s, n) => s + cost(n), 0);
  const heaviest = names.filter((n) => cost(n) > 0).sort((a, b) => cost(b) - cost(a)).slice(0, 3);
  return {
    cycles,
    percent: 100 * (budget.audio.stock + cycles / budget.audio.block),
    over: cycles > budget.limits.cpu,
    heaviest,
  };
}

export function overBudget(load: AudioLoad, title: (name: string) => string = (n) => n): string {
  return `Audio CPU over budget: ~${Math.round(load.percent)} % of each audio block. The build works, but the UI may lag `
    + `and the sound may drop out. Heaviest: ${load.heaviest.map(title).join(", ")}.`;
}
