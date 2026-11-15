// Build a preview of all deck slides and measure overflow in headless Chrome.
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const DECK = process.argv[2];
const deck = JSON.parse(readFileSync(join(DECK, 'project/deck.json'), 'utf8'));
const head = readFileSync(join(DECK, 'preview.html'), 'utf8').split('<body>')[0] + '<body>\n';
let body = deck.order.map((id) => readFileSync(join(DECK, 'project/slides', id + '.html'), 'utf8')).join('');
body = body.replaceAll('/_blob/7e5ad03e4af8f9937e330ccfebedd909', 'oldmap.png').replaceAll('/_blob/e4cac0f431e17138de9683e260b43861', 'oldshot.jpg')
  .replaceAll('/_blob/545b189ba67de2bd7d8a28042ff799d5', '../shots/beginner_cards.png').replaceAll('/_blob/1324f07e8d923a9f7ffbc352ba87fe5d', '../shots/advanced_lowrisk_crop.png');
writeFileSync(join(DECK, 'preview.html'), head + body + '</body></html>');

const PORT = 9334, sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${mkdtempSync(join(tmpdir(), 'rc-m-'))}`, '--allow-file-access-from-files', '--window-size=1920,1080', 'about:blank'], { stdio: 'ignore' });
let ws, id = 0; const pending = new Map();
for (let i = 0; i < 40 && !ws; i++) { try { const p = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find((t) => t.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); await new Promise((r) => ws.addEventListener('open', r)); } } catch {} await sleep(250); }
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send('Page.navigate', { url: pathToFileURL(join(DECK, 'preview.html')).href }); await sleep(4000);
const expr = `(async()=>{await document.fonts.ready; document.getAnimations().forEach(a=>{try{a.finish()}catch(e){}});
 const out=[]; document.querySelectorAll('body > section').forEach(sec=>{const sr=sec.getBoundingClientRect(); let maxB=0; const probs=[];
 sec.querySelectorAll('h1,h2,h3,p,img,div,svg').forEach(el=>{ if(el.closest('svg')&&el.tagName!=='svg') return; if(el.closest('.foot')) return; const r=el.getBoundingClientRect(); if(!r.width) return;
 const full=el.tagName==='svg'&&r.width>=1900; const right=r.right-sr.left, bottom=r.bottom-sr.top; if(!full) maxB=Math.max(maxB,bottom);
 if(!full && (right>1793 || bottom>953)) probs.push(el.tagName+'.'+(el.className.baseVal??el.className)+' r='+Math.round(right)+' b='+Math.round(bottom));
 if((el.tagName==='P'||el.tagName.startsWith('H')) && el.scrollWidth>el.clientWidth+2) probs.push('hscroll '+el.textContent.slice(0,30)); });
 const f=sec.querySelector('.foot'); if(f){const r=f.getBoundingClientRect(); if(r.right-sr.left>1793 || f.scrollWidth>f.clientWidth+2) probs.push('foot overflow');}
 out.push(sec.id+' maxB='+Math.round(maxB)+' '+(probs.slice(0,5).join(' | ')||'ok'))}); return out.join('\\n')})()`;
const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
console.log(r.result?.result?.value ?? JSON.stringify(r));
ws.close(); chrome.kill();
