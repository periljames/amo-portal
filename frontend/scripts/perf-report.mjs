import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

const distDir = path.resolve('dist/assets');
if (!fs.existsSync(distDir)) {
  console.error('dist/assets not found. Run npm run build first.');
  process.exit(1);
}

const files = fs.readdirSync(distDir).filter((f) => f.endsWith('.js') || f.endsWith('.css'));
const rows = files.map((name) => {
  const full = path.join(distDir, name);
  const buf = fs.readFileSync(full);
  return {
    file: name,
    bytes: buf.byteLength,
    gzip: zlib.gzipSync(buf).byteLength,
    brotli: zlib.brotliCompressSync(buf).byteLength,
  };
}).sort((a, b) => b.bytes - a.bytes);

const total = rows.reduce((acc, r) => ({
  bytes: acc.bytes + r.bytes,
  gzip: acc.gzip + r.gzip,
  brotli: acc.brotli + r.brotli,
}), { bytes: 0, gzip: 0, brotli: 0 });

const top = rows.slice(0, 12);
const report = { generatedAt: new Date().toISOString(), totals: total, top, count: rows.length };

fs.writeFileSync(path.resolve('dist/perf-report.json'), JSON.stringify(report, null, 2));

console.log('Top chunks by raw size:');
for (const r of top) {
  console.log(`${r.file}\traw=${r.bytes}\tgzip=${r.gzip}\tbrotli=${r.brotli}`);
}
console.log(`TOTAL\traw=${total.bytes}\tgzip=${total.gzip}\tbrotli=${total.brotli}\tfiles=${rows.length}`);
console.log('Wrote dist/perf-report.json');
