// Actual render functions in a strict DOM-ID VM. Not browser layout/paint.
import vm from 'node:vm';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {performance} from 'node:perf_hooks';
import {webcrypto} from 'node:crypto';
const [base,out]=process.argv.slice(2),store=new Map();
const html=await fs.readFile(new URL('../canary_ssm/web/index.html',import.meta.url),'utf8');
const ids=new Set([...html.matchAll(/\bid=["']([^"']+)["']/g)].map(x=>x[1]));
const elements=new Map();
const el=id=>{assert.ok(ids.has(id),'Unknown DOM ID '+id);if(!elements.has(id))elements.set(id,{id,textContent:'',innerHTML:'',className:'',value:'',checked:false,hidden:false,disabled:false,files:[],listeners:{},addEventListener(n,f){this.listeners[n]=f;},setAttribute(){}});return elements.get(id);};
const context=vm.createContext({document:{getElementById:el,addEventListener(){}},URLSearchParams,URL,location:{search:'',hash:''},sessionStorage:{getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},performance,Date,Math,Number,String,Object,JSON,console,crypto:webcrypto,AbortSignal,fetch:(url,opts)=>fetch(new URL(url,base),opts),setInterval:()=>0,setTimeout:()=>0,Uint8Array,btoa:s=>Buffer.from(s,'binary').toString('base64')});
for(const file of ['app.js','console.js'])vm.runInContext(await fs.readFile(new URL('../canary_ssm/web/'+file,import.meta.url),'utf8'),context);
await vm.runInContext('fetchState()',context);await vm.runInContext('fetchCatalog()',context);
const rows=['component,sample,elapsed_ns,scope'];
for(let i=0;i<100;i++){
 const start=performance.now();vm.runInContext('render();renderDashboard()',context);rows.push(`vm_public_renderer,${i},${Math.round((performance.now()-start)*1e6)},real app renderer in strict DOM VM; no browser layout paint`);
}
for(let i=0;i<20;i++){
 const start=performance.now();await vm.runInContext('fetchState()',context);rows.push(`http_vm_render,${i},${Math.round((performance.now()-start)*1e6)},actual HTTP plus app render; no browser layout paint`);
}
await fs.writeFile(out,rows.join('\n')+'\n');console.log(JSON.stringify({samples:rows.length-1,real_html_ids:true,browser_layout_paint:false}));
