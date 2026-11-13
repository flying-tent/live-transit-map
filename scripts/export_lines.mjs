// docs/maps.js から「地図ID → 路線（ID・名前・駅名の並び）」を取り出して JSON で出力する。
// 使い方: node scripts/export_lines.mjs > build/lines.json
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const here = fileURLToPath(new URL('.', import.meta.url));
const code = readFileSync(`${here}../docs/maps.js`, 'utf8');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(code + '\n;globalThis.__MAPS = MAPS;', ctx);

const out = {};
for (const [mapId, M] of Object.entries(ctx.__MAPS)) {
  out[mapId] = {
    title: M.title,
    lines: M.lines.map(l => ({
      id: l.id,
      name: l.name,
      stations: l.nodes.filter(n => typeof n === 'string'),
      loop: !!l.loop,
    })),
  };
}
process.stdout.write(JSON.stringify(out, null, 1));
