'use strict';
const $ = (selector) => document.querySelector(selector);
let csrfToken = '';
const escapeHTML = (v) => String(v ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
async function api(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET' && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(url, {...options, headers, credentials:'same-origin'});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'تعذر إكمال الطلب');
  return data;
}
function showPortal(visible) { $('#loginPanel').classList.toggle('hidden', visible); $('#portal').classList.toggle('hidden', !visible); }
async function loadTickets() {
  const data = await api('/api/employee/tickets');
  const root = $('#ticketList');
  if (!data.tickets.length) { root.className = 'employee-empty'; root.textContent = 'لا توجد بلاغات حتى الآن.'; return; }
  root.className = '';
  root.innerHTML = data.tickets.map(ticket => `<article class="employee-ticket"><h3>#${ticket.id} · ${escapeHTML(ticket.title)}</h3><div class="employee-meta">${escapeHTML(ticket.status)} · ${escapeHTML(ticket.priority)} · ${new Date(ticket.created_at).toLocaleString('ar')}</div><p>${escapeHTML(ticket.description)}</p><strong>التحديثات</strong><ul>${ticket.events.map(event => `<li>${escapeHTML(event.event)} — ${new Date(event.created_at).toLocaleString('ar')}${event.note ? `<p>${escapeHTML(event.note)}</p>` : ''}</li>`).join('')}</ul>${ticket.status === 'Resolved' ? `<button class="btn secondary reopen-ticket" data-ticket="${ticket.id}" type="button">طلب إعادة فتح البلاغ</button>` : ''}</article>`).join('');
}
async function initializePortal() {
  const session = await api('/api/session'); csrfToken = session.csrf_token;
  if (!session.user) { showPortal(false); return; }
  if (session.user.role !== 'employee') { location.href = '/'; return; }
  showPortal(true);
  const assets = await api('/api/employee/assets');
  $('#assetOptions').innerHTML = '<option value="">بدون أصل محدد</option>' + assets.assets.map(asset => `<option value="${asset.id}">${escapeHTML(asset.asset_tag)} — ${escapeHTML(asset.name)}</option>`).join('');
  await loadTickets();
}
$('#loginForm').addEventListener('submit', async event => {
  event.preventDefault(); $('#loginError').textContent = '';
  const form = event.currentTarget;
  try {
    const result = await api('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:form.elements.username.value,password:form.elements.password.value})});
    csrfToken = result.csrf_token; form.reset(); await initializePortal();
  } catch (error) { $('#loginError').textContent = error.message; }
});
$('#ticketForm').addEventListener('submit', async event => {
  event.preventDefault(); $('#ticketError').textContent = '';
  const form = event.currentTarget;
  const item = {title:form.elements.title.value, description:form.elements.description.value, asset_id:form.elements.asset_id.value ? Number(form.elements.asset_id.value) : null, category:form.elements.category.value, impact:Number(form.elements.impact.value), urgency:Number(form.elements.urgency.value)};
  try {
    const result = await api('/api/employee/tickets', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});
    form.reset(); $('#ticketError').textContent = `تم إرسال البلاغ بنجاح. الرقم المرجعي: #${result.id}`; await loadTickets();
  } catch (error) { $('#ticketError').textContent = error.message; }
});
$('#logoutButton').addEventListener('click', async () => {
  try { await api('/api/logout', {method:'POST'}); } catch (_) { /* Expired sessions are already logged out. */ }
  csrfToken = ''; showPortal(false);
});
$('#ticketList').addEventListener('click', async event => {
  const button = event.target.closest('.reopen-ticket');
  if (!button) return;
  try { await api(`/api/employee/tickets/${button.dataset.ticket}/reopen`, {method:'POST'}); await loadTickets(); }
  catch (error) { $('#ticketError').textContent = error.message; }
});
initializePortal().catch(() => showPortal(false));
