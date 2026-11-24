// Browser check of the comment layer (needs Google Chrome; not part of npm test):
//   node l3/l3-plan-render/tests/browser_comments.mjs
// Serves a copy of fixtures/simple, comments on a code line and a flow node, answers q1,
// then asserts the rows in plan.state.json point at the right plan.md lines.
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const HERE = path.dirname(new URL(import.meta.url).pathname);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pp-browser-'));
fs.cpSync(path.join(HERE, 'fixtures/simple/plan.md'), path.join(tmp, 'plan/plan.md'), { recursive: true });
const env = { ...process.env, CLAUDE_PLAN_PILOT_HOME: path.join(tmp, 'home') };
const SERVE = path.join(HERE, '../scripts/serve.py');
const url = execFileSync('python3', [SERVE, 'start', path.join(tmp, 'plan')], { env }).toString().trim().split('\n').pop();
const profile = path.join(tmp, 'profile');
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', ['--headless=new', '--remote-debugging-port=9333', '--user-data-dir=' + profile, '--window-size=1200,1600', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets;
for (let i = 0; i < 50; i++) { try { targets = await (await fetch('http://127.0.0.1:9333/json')).json(); break; } catch { await sleep(200); } }
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = {};
ws.addEventListener('message', (m) => { const d = JSON.parse(m.data); if (d.id && pending[d.id]) { pending[d.id](d); delete pending[d.id]; } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); return r.result.result.value ?? r.result.exceptionDetails?.exception?.description; };
await send('Page.enable'); await send('Runtime.enable');
const errs = []; ws.addEventListener('message', (m) => { const d = JSON.parse(m.data); if (d.method === 'Runtime.exceptionThrown') errs.push(d.params.exceptionDetails.exception?.description); });
await send('Page.navigate', { url: url + '#p-01' }); await sleep(2500);
const mouse = async (x, y, type) => send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
// 1) select a code line's text, mouseup -> Comment button -> popover -> save
const box = await ev(`(() => { const ln = document.querySelector('#p-01 .ln-bug'); ln.scrollIntoView({block:'center'}); const r = document.createRange(); r.selectNodeContents(ln); getSelection().removeAllRanges(); getSelection().addRange(r); const b = ln.getBoundingClientRect(); return {x:b.left+40,y:b.top+5, md: ln.dataset.md}; })()`);
await mouse(box.x, box.y, 'mouseReleased'); await sleep(300);
const addBtn = await ev(`(() => { const b = document.querySelector('.c-add'); if(!b) return null; b.click(); return true; })()`); await sleep(200);
await ev(`(() => { const t = document.querySelector('.c-pop textarea'); t.value = 'why prorate here?'; [...document.querySelectorAll('.c-pop button')].find(b=>b.textContent==='Save comment').click(); return 1; })()`); await sleep(1200);
// 2) click a flow node in the Context fold
const nb = await ev(`(() => { document.querySelector('#p-context details').open = true; const n = document.querySelector('[data-node="prorate"]'); n.scrollIntoView({block:'center'}); const b = n.getBoundingClientRect(); return {x:b.left+b.width/2,y:b.top+b.height/2, md:n.dataset.md}; })()`);
await sleep(200); await mouse(nb.x, nb.y, 'mousePressed'); await mouse(nb.x, nb.y, 'mouseReleased'); await sleep(300);
const add2 = await ev(`(() => { const b = document.querySelector('.c-add'); if(!b) return null; b.click(); return true; })()`); await sleep(200);
await ev(`(() => { const t = document.querySelector('.c-pop textarea'); t.value = 'node comment'; [...document.querySelectorAll('.c-pop button')].find(b=>b.textContent==='Save comment').click(); return 1; })()`); await sleep(1200);
// 3) answer q1 via radio
await ev(`(() => { document.querySelector('#tab-questions').click(); document.querySelector('#q1-carry').click(); return 1; })()`); await sleep(1500);
const copyText = await ev(`(() => { const items = [...document.querySelectorAll('.c-item')].map(i => i.querySelector('.c-ref').textContent); return items; })()`);
const pins = await ev(`document.querySelectorAll('.c-pin').length`);
const sync = await ev(`document.querySelector('#q-sync').textContent`);
const out = { codeLine: box.md, node: nb.md, refs: copyText, pins, errs };
ws.close(); chrome.kill();
execFileSync('python3', [SERVE, 'stop', '--all'], { env });
const st = JSON.parse(fs.readFileSync(path.join(tmp, 'plan/plan.state.json'), 'utf8'));
const lines = fs.readFileSync(path.join(tmp, 'plan/plan.md'), 'utf8').split('\n');
const rows = Object.values(st.comments);
const fail = [];
if (st.answers?.q1?.choice !== 'carry') fail.push('q1 answer not saved');
const code = rows.find((r) => !r.node), node = rows.find((r) => r.node === 'prorate');
if (!code || !lines[+code.md.split('-')[0] - 1].includes('prorate(sub.Plan.Price')) fail.push('code comment line wrong: ' + JSON.stringify(code));
if (!node || !lines[+node.md.split('-')[0] - 1].includes('"id": "prorate"')) fail.push('node comment line wrong: ' + JSON.stringify(node));
if (errs.length) fail.push('page errors: ' + errs.join('; '));
console.log(JSON.stringify(out, null, 1));
console.log(fail.length ? 'FAIL\n' + fail.join('\n') : 'OK');
process.exit(fail.length ? 1 : 0);
