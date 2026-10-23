'use strict';
const $ = (selector) => document.querySelector(selector);
const API = async (url, options = {}) => {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET' && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(url, {...options, headers, credentials:'same-origin'});
  const content = await response.json();
  if (!response.ok) throw new Error(content.error || 'Request failed');
  return content;
};
const escapeHTML = (v) => String(v ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
const date = (v) => v ? new Date(v).toLocaleString([], {dateStyle:'medium', timeStyle:'short'}) : '—';
const statusTag = (v) => `<span class="status ${v === 'Open' ? 'open' : v === 'Resolved' ? 'resolved' : 'progress'}">${escapeHTML(v)}</span>`;
const priorityTag = (v) => `<span class="priority ${escapeHTML(v)}">${escapeHTML(v)}</span>`;
let activeTicket = null;
let assets = [];
let csrfToken = '';
let currentRole = null;
let toastTimer;
function toast(message) {
  const el = $('#toast'); el.textContent = message; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 3600);
}
const headings = {
  overview: ['Operations overview','Incident visibility, response priorities and asset health — in one place.'],
  incidents: ['Incident management','Review outstanding incidents, change states and document actions.'],
  assets: ['Asset registry','A compact inventory connected directly to incident records.']
};
async function switchView(target) {
  document.querySelectorAll('.view').forEach(el => el.classList.toggle('hidden', el.id !== `view-${target}`));
  document.querySelectorAll('.nav-link').forEach(el => el.classList.toggle('active', el.dataset.view === target));
  $('#crumb').textContent = target.toUpperCase(); $('#pageTitle').textContent = headings[target][0]; $('#pageIntro').textContent = headings[target][1];
  if(target === 'overview') await refreshOverview();
  if(target === 'incidents') await refreshTickets();
  if(target === 'assets') await refreshAssets();
}
const makeRows = (list, compact=false) => list.length ? `<table><thead><tr><th>INCIDENT</th><th>PRIORITY</th><th>STATUS</th><th>SLA DEADLINE</th><th></th></tr></thead><tbody>${list.map(t => `<tr><td><div class="row-title">#${t.id} · ${escapeHTML(t.title)}</div><div class="row-sub">${escapeHTML(t.asset_tag)}</div></td><td>${priorityTag(t.priority)}</td><td>${statusTag(t.status)}</td><td>${date(t.due_at)} ${t.breached ? '<div class="breach">BREACHED</div>' : ''}</td><td><button class="ticket-open" data-ticket="${t.id}">Open ↗</button></td></tr>`).join('')}</tbody></table>` : `<p class="empty">No incidents match your filters.</p>`;
async function refreshOverview() {
  const d = await API('/api/dashboard');
  const labels = [['OPEN INCIDENTS',d.open,'blue'], ['SLA BREACHES',d.breached,'red'], ['RESOLVED',d.resolved,''], ['REGISTERED ASSETS',d.assets,'']];
  $('#stats').innerHTML = labels.map(([label,count,color]) => `<div class="stat ${color}"><span class="stat-label">${label}</span><strong>${count}</strong></div>`).join('');
  $('#recent').innerHTML = makeRows(d.recent,true);
}
async function refreshTickets() {
  const qs = new URLSearchParams();
  if ($('#ticketSearch').value) qs.set('q',$('#ticketSearch').value);
  if ($('#statusFilter').value) qs.set('status',$('#statusFilter').value);
  const data = await API('/api/tickets' + (qs.size ? `?${qs}` : ''));
  $('#ticketTable').innerHTML = makeRows(data.tickets);
}
async function refreshAssets() {
  assets = (await API('/api/assets')).assets;
  $('#assetTable').innerHTML = `<table><thead><tr><th>ASSET TAG</th><th>DEVICE</th><th>CATEGORY</th><th>LOCATION</th><th>STATUS</th></tr></thead><tbody>${assets.map(a => `<tr><td>${escapeHTML(a.asset_tag)}</td><td>${escapeHTML(a.name)}</td><td>${escapeHTML(a.category)}</td><td>${escapeHTML(a.location)}</td><td>${statusTag(a.state)}</td></tr>`).join('')}</tbody></table>`;
  $('#assetOptions').innerHTML = assets.map(a => `<option value="${a.id}">${escapeHTML(a.asset_tag)} — ${escapeHTML(a.name)}</option>`).join('');
}
async function viewTicket(id) {
  activeTicket = id;
  const t = await API(`/api/tickets/${id}`);
  $('#ticketTitle').textContent = `#${t.id} — ${t.title}`;
  $('#ticketDetail').innerHTML = `<div class="detail-grid"><div class="detail-field">ASSET<strong>${escapeHTML(t.asset_tag || 'Not specified')}</strong></div><div class="detail-field">CATEGORY<strong>${escapeHTML(t.category)}</strong></div><div class="detail-field">ASSIGNED TO<strong>${escapeHTML(t.assigned_username || 'Unassigned')}</strong></div><div class="detail-field">PRIORITY<strong>${priorityTag(t.priority)}</strong></div><div class="detail-field">STATUS<strong>${statusTag(t.status)}</strong></div><div class="detail-field">SLA DEADLINE<strong>${date(t.due_at)}${t.breached?' · BREACHED':''}</strong></div><div class="detail-field">REPORTED<strong>${date(t.created_at)}</strong></div><div class="detail-field">RESOLVED<strong>${date(t.resolved_at)}</strong></div></div><p>${escapeHTML(t.description || 'No description provided.')}</p>${currentRole === 'admin' ? '<form id="assignmentForm" class="status-form"><label>Assign technician<select name="technician_id" required></select></label><button class="btn secondary" type="submit">Save assignment</button></form>' : ''}<h3>Audit timeline</h3><ul class="event-list">${t.events.map(e => `<li><strong>${escapeHTML(e.event)}</strong><small>${date(e.created_at)}</small>${e.note ? `<p>${escapeHTML(e.note)}</p>` : ''}</li>`).join('')}</ul>`;
  if (currentRole === 'admin') {
    const technicians = (await API('/api/technicians')).technicians;
    $('#assignmentForm').elements.technician_id.innerHTML = technicians.map(person => `<option value="${person.id}" ${person.id === t.assigned_to ? 'selected' : ''}>${escapeHTML(person.username)}</option>`).join('');
    $('#assignmentForm').addEventListener('submit', async event => {
      event.preventDefault();
      try { await API(`/api/tickets/${id}/assign`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({technician_id:Number(event.currentTarget.elements.technician_id.value)})}); toast(`Incident #${id} assigned`); await viewTicket(id); await refreshTickets(); }
      catch(error) { toast(error.message); }
    });
  }
  $('#nextStatus').value = t.status;
  $('#statusForm').elements.note.value = '';
  $('#ticketDialog').showModal();
}
async function submitTicket(event) {
  event.preventDefault();
  const f = event.currentTarget;
  const item = {title:f.elements.title.value,description:f.elements.description.value,
      asset_id:Number(f.elements.asset_id.value),impact:Number(f.elements.impact.value),urgency:Number(f.elements.urgency.value)};
  try {
    const result = await API('/api/tickets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});
    $('#createDialog').close(); f.reset(); toast(`Incident #${result.id} created (${result.priority})`);
    await switchView('incidents');
  } catch(err) { toast(err.message); }
}
async function submitStatus(event) {
  event.preventDefault(); const f=event.currentTarget;
  if (f.elements.status.value === 'Resolved' && !f.elements.note.value.trim()) { toast('Add a resolution note before resolving this ticket'); return; }
  try {
    await API(`/api/tickets/${activeTicket}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:f.elements.status.value,note:f.elements.note.value})});
    $('#ticketDialog').close(); toast(`Incident #${activeTicket} updated`);
    await refreshTickets(); await refreshOverview();
  } catch(err) { toast(err.message); }
}
document.addEventListener('click', async event => {
  const nav = event.target.closest('[data-view]');
  if(nav) { try { await switchView(nav.dataset.view); } catch(e) {toast(e.message)} }
  const ticket = event.target.closest('[data-ticket]');
  if(ticket) { try { await viewTicket(Number(ticket.dataset.ticket)); } catch(e) { toast(e.message); } }
  const close = event.target.closest('[data-close]');
  if(close) document.getElementById(close.dataset.close).close();
});
$('#newTicketTop').addEventListener('click',() => $('#createDialog').showModal());
$('#createForm').addEventListener('submit',submitTicket);
$('#statusForm').addEventListener('submit',submitStatus);
let searchTimer;
$('#ticketSearch').addEventListener('input',() => {clearTimeout(searchTimer); searchTimer=setTimeout(()=>refreshTickets().catch(e=>toast(e.message)),160)});
$('#statusFilter').addEventListener('change',() => refreshTickets().catch(e=>toast(e.message)));
$('#clock').textContent = new Date().toLocaleDateString([], {month:'short',day:'numeric',year:'numeric'});
async function bootstrap() {
  const session = await API('/api/session'); csrfToken = session.csrf_token;
  if (!session.user) { $('#loginGate').classList.remove('hidden'); return; }
  currentRole = session.user.role;
  if (session.user.role === 'employee') { location.href = '/employee'; return; }
  $('#appShell').classList.remove('hidden');
  await Promise.all([refreshAssets(),refreshOverview()]);
}
$('#operatorLogin').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.currentTarget;
  try {
    const result = await API('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:form.elements.username.value,password:form.elements.password.value})});
    csrfToken = result.csrf_token;
    currentRole = result.user.role;
    if (result.user.role === 'employee') { location.href = '/employee'; return; }
    $('#loginGate').classList.add('hidden'); $('#appShell').classList.remove('hidden'); form.reset();
    await Promise.all([refreshAssets(),refreshOverview()]);
  } catch (error) { $('#loginError').textContent = error.message; }
});
$('#logoutButton').addEventListener('click', async () => {
  try { await API('/api/logout',{method:'POST'}); } finally { location.reload(); }
});
bootstrap().catch(e=>{ $('#loginGate').classList.remove('hidden'); $('#loginError').textContent=`Unable to load demo: ${e.message}`; });
