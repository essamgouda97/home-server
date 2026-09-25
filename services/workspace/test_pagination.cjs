// Exercise the actual UI pagination functions with deferred, isolated responses.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/static/app.js','utf8');
function element(){return {children:[],value:'',hidden:false,disabled:false,selectedOptions:[{textContent:'All documents'}],append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},setAttribute(){}}}
function harness(){
 const nodes=new Map();
 const context={AbortController,Date,Number,Map,Set,state:{document:null},document:{createElement:element},$:id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)},text:()=>element(),empty:target=>target.replaceChildren(),work:()=>{},openDocument:()=>{},notice:()=>{}};
 context.call=async()=>({count:65,next:2,previous:null,results:Array.from({length:30},(_,i)=>({id:i,title:'Synthetic',added:'2026-09-24'}))});
 vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('let documentRequest='),source.indexOf('async function openDocument('))+'\nglobalThis.load=loadDocuments;',context);
 return {context,nodes};
}
(async()=>{
 const {context:c,nodes}=harness();
 await c.load();assert.equal(nodes.get('documents').children.length,30);assert.equal(c.state.documentPage,1);
 for(let page=2;page<=10;page++){await c.load(page);assert.equal(nodes.get('documents').children.length,30)}
 c.call=async()=>{throw Error('Synthetic failure')};
 await assert.rejects(c.load(11));assert.equal(c.state.documentPage,10);assert.equal(nodes.get('documents').children.length,30);assert.equal(nodes.get('document-next').disabled,false);
 let oldResolve,newResolve;
 c.call=()=>new Promise(resolve=>{if(!oldResolve)oldResolve=resolve;else newResolve=resolve});
 const old=c.load(1),current=c.load(2);
 newResolve({count:0,next:null,previous:1,results:[]});await current;
 oldResolve({count:100,next:2,previous:null,results:[]});await old;
 assert.equal(c.state.documentPage,2);assert.equal(nodes.get('document-count').textContent,'0 documents');
 const groupSource=source.slice(source.indexOf('let groupRequest='),source.indexOf('function renderDocumentGroups('));
 c.renderDocumentGroups=()=>{};
 let requests=0;c.call=async()=>{requests++;return {count:90,next:2,previous:null,results:Array.from({length:30},(_,i)=>({id:i+1,name:'Group '+i}))}};
 vm.runInContext(groupSource+'\nglobalThis.groups=loadGroups;',c);
 await c.groups();assert.equal(requests,1);assert.equal(c.state.groups.length,30);assert.equal(c.state.groupNext,2);
 console.log('PASS bounded document DOM, failed-page recovery, stale-response protection, and one-page group loading');
})().catch(error=>{console.error(error);process.exitCode=1});
