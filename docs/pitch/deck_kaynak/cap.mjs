// Drive local headless Chrome via CDP (Node 24 built-in WebSocket) to screenshot Rotacast result cards.
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = dirname(fileURLToPath(import.meta.url));
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const PORT = 9333;
const profile = mkdtempSync(join(tmpdir(), 'rc-shot-'));
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--window-size=1440,1000', '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let ws, id = 0; const pending = new Map();
async function connect() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = list.find((t) => t.type === 'page');
      if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); await new Promise((r) => ws.addEventListener('open', r)); break; }
    } catch { /* not up yet */ }
    await sleep(250);
  }
  ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
}
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evaluate = async (expr) => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;

async function run(mode) {
  await send('Page.navigate', { url: 'http://localhost:8003/' }); await sleep(1500);
  await evaluate(`localStorage.setItem('rotacast.mode','${mode}'); location.reload(); 1`); await sleep(3000);
  await evaluate(`[...document.querySelectorAll('button')].find(x=>x.innerText.trim().startsWith('Merkez ova'))?.click(); 1`); await sleep(800);
  await evaluate(`[...document.querySelectorAll('button')].find(x=>x.innerText.trim()==='Tarlamı analiz et')?.click(); 1`);
  for (let i = 0; i < 60; i++) { await sleep(1000); if (await evaluate(`/Rotasyonları karşılaştır|Seçenekleriniz kısaca/.test(document.body.innerText)`)) break; }
  await sleep(2500);
}

async function shot(name, selectorExpr) {
  const box = await evaluate(`(()=>{const el=${selectorExpr}; if(!el) return null; el.scrollIntoView({block:'start'}); const r=el.getBoundingClientRect(); return {x:r.left+scrollX, y:r.top+scrollY, w:r.width, h:r.height, txt: el.innerText}})()`);
  if (!box) { console.log(name, 'NOT FOUND'); return; }
  await sleep(500);
  const res = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: box.x - 8, y: box.y - 8, width: box.w + 16, height: box.h + 16, scale: 2 } });
  writeFileSync(join(OUT, name + '.png'), Buffer.from(res.result.data, 'base64'));
  console.log(name, Math.round(box.w), 'x', Math.round(box.h), 'hesaplanmad:', /hesaplanmad/i.test(box.txt));
}

await connect();
await send('Page.enable'); await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });

await run('beginner');
const grid = `(()=>{const l=[...document.querySelectorAll('button,a')].find(e=>/Ayrıntıları gör/.test(e.textContent)); let c=l; while(c && !/MEVCUT|YILLIK DÖNGÜ/i.test((c.innerText||'').slice(0,40))) c=c.parentElement; return c.parentElement})()`;
await shot('beginner_cards', grid);

await run('advanced');
const cardByTitle = (t) => `(()=>{const h=[...document.querySelectorAll('h3,h4,p,div,span')].filter(e=>e.childElementCount<=2 && e.textContent.trim().endsWith('${t}')); for (const x of h){ let c=x; for(let i=0;i<8&&c;i++){ c=c.parentElement; const r=c.getBoundingClientRect(); if(r.width>300 && r.width<760 && r.height>400) return c; } } return null})()`;
await shot('advanced_lowrisk', cardByTitle('Düşük riskli ve dayanıklı'));
await shot('advanced_baseline', cardByTitle('Mevcut rotasyon'));
const all = await evaluate(`[...document.body.innerText.matchAll(/[^\\n]*hesaplanmad[^\\n]*/gi)].map(m=>m[0]).slice(0,8)`);
console.log('advanced page lines with hesaplanmad:', JSON.stringify(all));

ws.close(); chrome.kill();
