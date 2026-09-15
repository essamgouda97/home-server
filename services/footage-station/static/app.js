'use strict';
const $ = id => document.getElementById(id);
let snapshot, selected, selectionVersion = '', listVersion = '', busy = false;
const text = (id, value) => { $(id).textContent = value; };
const bytes = n => { const v = Number(n || 0); return v < 1048576 ? `${Math.round(v / 1024)} KB` : v < 1073741824 ? `${(v / 1048576).toFixed(1)} MB` : `${(v / 1073741824).toFixed(1)} GB`; };
const date = value => value ? new Date(value).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : 'No update yet';
function message(id, value) { text(id, value); $(id).hidden = !value; }
async function action(path, data) {
  if (busy) return;
  busy = true; message('error', '');
  try {
    const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not save. Try again.');
    message('notice', path === '/api/assign' ? 'Assignment saved.' : path === '/api/policy' ? 'Destination saved for new cards.' : 'Request queued. The page will update automatically.');
    await refresh();
  } catch (error) { message('error', error.message); } finally { busy = false; }
}
function renderDetail(force = false) {
  const row = snapshot?.imports.find(r => r.id === selected);
  $('detail-content').hidden = !row; $('detail-help').hidden = !!row;
  text('detail-title', row ? row.assignment.project : 'Select an import');
  if (!row) return;
  const version = JSON.stringify([row.id, row.assignment]);
  if (force || (version !== selectionVersion && !$('assignment').contains(document.activeElement))) {
    $('project').value = row.assignment.project; $('session').value = row.assignment.session; selectionVersion = version;
  }
  text('import-info', `${row.file_count} files · ${bytes(row.total_bytes)} · ${row.verified_at ? 'Verified ' + date(row.verified_at) : (row.status || 'Importing')}`);
  const folder = `Creative/Projects/${row.project}/Originals/${row.card}/`;
  $('files-link').href = 'http://files.lan/files/' + folder.split('/').map(encodeURIComponent).join('/');
  text('manifest', row.manifest || 'A completion manifest is published after every file is verified.');
  text('codex-state', row.codex.status);
  text('codex-basis', 'Basis: file names and sizes. Visual scene clustering is a later stage.');
  text('codex-output', row.codex.notes || row.codex.error || (row.codex.status === 'running' ? 'Codex is reviewing this import…' : 'A review will appear here when the server finishes processing this import.'));
  $('codex-retry').disabled = !row.verified_at || ['queued','running'].includes(row.codex.status);
}
function renderList() {
  const query = $('search').value.toLowerCase();
  const rows = snapshot.imports.filter(r => [r.assignment.project,r.assignment.session,r.card].some(s => s.toLowerCase().includes(query)));
  const version=JSON.stringify([selected,query,rows.map(r=>[r.id,r.assignment,r.file_count,r.total_bytes,r.verified_at,r.status])]);
  if(version===listVersion)return;listVersion=version;
  $('imports').replaceChildren(); text('count', snapshot.imports.length);
  $('empty').hidden = snapshot.imports.length > 0;
  if (!rows.length && snapshot.imports.length) {
    const p = document.createElement('p'); p.textContent = 'No matching imports. Try another project or card name.'; $('imports').append(p);
  }
  for (const row of rows) {
    const button = document.createElement('button'); button.className = 'import-row' + (selected === row.id ? ' selected' : ''); button.type='button'; button.setAttribute('aria-pressed', String(selected === row.id));
    for (const [tag, cls, value] of [['strong','',row.assignment.project],['span','',row.assignment.session],['span','meta',`${row.file_count} files · ${bytes(row.total_bytes)} · ${date(row.verified_at || row.created_at)}`],['span',row.verified_at?'verified':'meta',row.verified_at?'✓ Original files verified':(row.status || 'Importing')]]) {
      const el=document.createElement(tag); el.className=cls; el.textContent=value; button.append(el);
    }
    button.onclick=()=>{selected=row.id;renderList();renderDetail(true);}; $('imports').append(button);
  }
}
function render() {
  const s=snapshot.station, online=snapshot.station_online;
  const states={waiting:['Ready for a camera card','Insert a card into the Pi’s USB reader. Importing starts automatically.'],mounting:['Reading camera card','The card is mounted read-only.'],scanning:['Preparing import','Finding files and choosing a stable destination.'],hashing:['Checking camera originals','Calculating checksums before copying.'],copying:['Copying to your server','Leave the card connected until verification and ejection finish.'],'checking-resume':['Resuming an import','Checking the saved copy before continuing.'],verifying:['Verifying copied file','Comparing the server copy with the camera original.'],'file-verified':['File verified','Continuing through the rest of the card.'],'verifying-import':['Verifying the full import','Checking every published file before recording completion.'],complete:['Originals verified','Waiting for the Pi to unmount the camera card.'],ejecting:['Preparing safe removal','Releasing the read-only camera mount.'],safe:['Safe to remove your card','The server copy is verified and the Pi has unmounted the card.'],failed:['Import needs attention',s.error || 'The station will retry automatically. Your camera originals are retained.']};
  const [title,desc]=online ? (states[s.phase] || ['Station connected','Waiting for the next progress update.']) : ['Waiting for the Pi',s.seen_at ? 'No recent station update. Check power and Ethernet; an extended verification can also delay updates.' : 'The tracking page is ready. Connect the prepared Pi with Ethernet and power for its first boot.'];
  text('station-title',title);text('station-description',desc);document.querySelector('.station').className='station '+(online?s.phase:'');
  text('current-file',online && !['waiting','safe'].includes(s.phase) ? s.file || '' : '');
  const active=online && s.total_bytes>0 && !['waiting','safe','failed'].includes(s.phase);
  $('progress').hidden=!active;$('progress').value= Math.min(100,100*(s.verified_bytes||0)/(s.total_bytes||1));
  text('progress-label',active?`${bytes(s.verified_bytes)} of ${bytes(s.total_bytes)} verified · File ${s.file_index||0} of ${s.file_count||0}`:`Last update: ${date(s.seen_at)}`);
  $('retry').hidden=!(online && s.phase==='failed');
  if (document.activeElement!==$('destination')) {
    const projects=[...new Set(['Inbox',snapshot.policy.project || 'Inbox',...snapshot.imports.map(r=>r.project)])];
    $('destination').replaceChildren(...projects.map(p=>{const o=document.createElement('option');o.value=p;o.textContent=p;return o;}));$('destination').value=snapshot.policy.project || 'Inbox';
  }
  text('worker-status',snapshot.worker.seen_at ? `Codex worker: ${snapshot.worker.status} · ${date(snapshot.worker.seen_at)}` : 'Codex worker has not reported yet.');
  renderList();renderDetail();
}
async function refresh(){
  try {const r=await fetch('/api/state');if(!r.ok)throw new Error('Server is unavailable. Retrying automatically.');snapshot=await r.json();render();text('connection','Updated just now');}
  catch(error){text('connection',error.message);}
}
$('search').oninput=()=>snapshot&&renderList();
$('assignment').onsubmit=e=>{e.preventDefault();action('/api/assign',{id:selected,project:$('project').value,session:$('session').value});};
$('destination').onchange=()=>action('/api/policy',{project:$('destination').value});
$('retry').onclick=()=>action('/api/retry',{});$('codex-retry').onclick=()=>action('/api/codex',{id:selected});
$('new-project').onclick=()=>{$('project-dialog').showModal();$('project-name').focus();};
$('cancel-project').onclick=()=>$('project-dialog').close();
$('project-form').onsubmit=e=>{e.preventDefault();const project=$('project-name').value;if(project.includes('..'))return message('error','Folder names cannot contain two consecutive dots.');$('project-dialog').close();action('/api/policy',{project});};
refresh();setInterval(()=>{if(!document.hidden)refresh();},4000);
