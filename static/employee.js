'use strict';
const $ = (selector) => document.querySelector(selector);
let csrfToken = '';
let language = localStorage.getItem('mihwar-language') === 'en' ? 'en' : 'ar';
let tickets = [];
const escapeHTML = (v) => String(v ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
const text = {
  ar: {
    brand:'مِحور',brandSub:'بوابة الموظفين · خدمات تقنية المعلومات',operatorSignIn:'دخول فريق الدعم',loginTitle:'تسجيل الدخول',loginIntro:'سجّل الدخول باستخدام بيانات الحساب التي زوّدك بها مسؤول النظام.',username:'اسم المستخدم',password:'كلمة المرور',signIn:'دخول',myRequests:'طلباتي',portalIntro:'قدّم طلب دعم جديدًا وتابع مستجداته من هنا.',signOut:'تسجيل الخروج',sampleNote:'تتضمن مساحة المراجعة الحالية بيانات أصول وبلاغات مولّدة لأغراض تقييم المنتج. هذه الأمثلة ليست سجلات تشغيل فعلية للمصنع. أما البلاغات التي تقدمها فتُحفظ في حسابك.',newRequest:'طلب دعم جديد',formIntro:'أخبرنا باختصار ما المشكلة وأين ظهرت. لا تحتاج إلى تقدير الأولوية؛ سيُسجّل الطلب بأولوية مبدئية ويراجعه فريق الدعم.',titleLabel:'عنوان مختصر للمشكلة',titlePlaceholder:'مثال: لا أستطيع الاتصال بشبكة الواي فاي',categoryLabel:'نوع الطلب',assetLabel:'الجهاز أو الأصل المرتبط (اختياري)',noAsset:'لا أعرف / لا ينطبق',descriptionLabel:'التفاصيل',descriptionPlaceholder:'ما الذي حدث؟ متى بدأ؟ وهل جرّبت أي خطوة لحل المشكلة؟',descriptionHint:'أضف رسالة الخطأ أو اسم النظام المتأثر إن أمكن، ولا تكتب كلمات مرور أو معلومات سرية.',submitRequest:'إرسال الطلب',trackRequests:'متابعة طلباتي',trackIntro:'ستظهر هنا الطلبات التي قدمتها والتحديثات التي يشاركها فريق الدعم.',loading:'جارٍ تحميل الطلبات…',catNetwork:'الشبكة والاتصال',catAccounts:'الحسابات والصلاحيات',catDevices:'الأجهزة والملحقات',catSoftware:'البرامج والخدمات',catOther:'أخرى',emptyTickets:'لم تقدم أي طلب بعد.',ticketNumber:'طلب رقم',updates:'آخر التحديثات',reopen:'طلب إعادة فتح الطلب',statusOpen:'مفتوح',statusProgress:'قيد المعالجة',statusResolved:'تم الحل',eventCreated:'تم استلام الطلب',eventReopened:'طلبت إعادة فتح البلاغ',eventUpdate:'تحديث من فريق الدعم',success:'تم إرسال طلبك بنجاح. رقمه المرجعي',invalidLogin:'اسم المستخدم أو كلمة المرور غير صحيحة.',loginLocked:'محاولات كثيرة غير ناجحة. انتظر قليلًا ثم حاول مجددًا.',titleError:'اكتب عنوانًا من 5 أحرف على الأقل.',descriptionError:'يرجى إضافة تفاصيل المشكلة.',genericError:'تعذر إكمال الطلب. حاول مجددًا أو تواصل مع فريق الدعم.'
  },
  en: {
    brand:'MIHWAR',brandSub:'Employee portal · IT services',operatorSignIn:'Support team sign in',loginTitle:'Sign in',loginIntro:'Use the account details provided by your system administrator.',username:'Username',password:'Password',signIn:'Sign in',myRequests:'My requests',portalIntro:'Submit a support request and follow its progress here.',signOut:'Sign out',sampleNote:'This review workspace contains generated sample assets and tickets for product evaluation. These examples are not records of actual plant operations. Requests you submit are saved to your account.',newRequest:'New support request',formIntro:'Briefly tell us what is wrong and where it happened. You do not need to estimate priority; a preliminary priority is assigned and the support team will review it.',titleLabel:'Short summary',titlePlaceholder:'For example: I cannot connect to the Wi-Fi',categoryLabel:'Request type',assetLabel:'Related device or asset (optional)',noAsset:'Not sure / not applicable',descriptionLabel:'What happened?',descriptionPlaceholder:'What happened, when did it start, and have you tried anything to fix it?',descriptionHint:'Include any error message or affected system if you can. Do not include passwords or confidential information.',submitRequest:'Submit request',trackRequests:'Track my requests',trackIntro:'Your submitted requests and updates from the support team will appear here.',loading:'Loading your requests…',catNetwork:'Network and connectivity',catAccounts:'Accounts and access',catDevices:'Devices and peripherals',catSoftware:'Software and services',catOther:'Other',emptyTickets:'You have not submitted a request yet.',ticketNumber:'Request',updates:'Updates',reopen:'Ask to reopen',statusOpen:'Open',statusProgress:'In progress',statusResolved:'Resolved',eventCreated:'Request received',eventReopened:'You asked to reopen this request',eventUpdate:'Update from support',success:'Your request was submitted. Reference number',invalidLogin:'The username or password is incorrect.',loginLocked:'There have been too many failed attempts. Wait a moment, then try again.',titleError:'Enter a title with at least 5 characters.',descriptionError:'Please describe the issue.',genericError:'We could not complete that request. Try again or contact the support team.'
  }
};
function tr(key) { return text[language][key] || text.en[key] || key; }
function translateError(message) {
  if (message === 'Invalid username or password') return tr('invalidLogin');
  if (message === 'Too many sign-in attempts. Try again later.') return tr('loginLocked');
  if (message === 'Title must be between 5 and 120 characters') return tr('titleError');
  if (message === 'Description too long' || message === 'Body must be a JSON object') return tr('descriptionError');
  return tr('genericError');
}
async function api(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET' && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  const response = await fetch(url, {...options, headers, credentials:'same-origin'});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function setLanguage(next) {
  language = next;
  localStorage.setItem('mihwar-language', language);
  document.documentElement.lang = language;
  document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
  document.title = language === 'ar' ? 'مِحور | بوابة الموظفين' : 'MIHWAR | Employee portal';
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = tr(el.dataset.i18n); });
  document.querySelectorAll('[data-placeholder]').forEach(el => { el.placeholder = tr(el.dataset.placeholder); });
  $('#languageButton').textContent = language === 'ar' ? 'English' : 'العربية';
  $('#languageButton').lang = language === 'ar' ? 'en' : 'ar';
  renderTickets();
}
function showPortal(visible) { $('#loginPanel').classList.toggle('hidden', visible); $('#portal').classList.toggle('hidden', !visible); }
function statusLabel(status) { return status === 'Resolved' ? tr('statusResolved') : status === 'In Progress' ? tr('statusProgress') : tr('statusOpen'); }
function eventLabel(event) {
  if (event === 'Created') return tr('eventCreated');
  if (event === 'Reopened') return tr('eventReopened');
  if (event === 'Update') return tr('eventUpdate');
  if (event.startsWith('Status: ')) return `${language === 'ar' ? 'تغيّرت الحالة من' : 'Status changed from'} ${statusLabel(event.slice(8).split(' → ')[0])} ${language === 'ar' ? 'إلى' : 'to'} ${statusLabel(event.slice(8).split(' → ')[1] || '')}`;
  return event;
}
function formatDate(value) { return new Date(value).toLocaleString(language === 'ar' ? 'ar' : 'en', {dateStyle:'medium',timeStyle:'short'}); }
function renderTickets() {
  const root = $('#ticketList');
  if (!root) return;
  if (!tickets.length) { root.className = 'employee-empty'; root.textContent = tr('emptyTickets'); return; }
  root.className = '';
  root.innerHTML = tickets.map(ticket => `<article class="employee-ticket"><div class="ticket-title-row"><h3>${tr('ticketNumber')} #${ticket.id} · ${escapeHTML(ticket.title)}</h3><span class="status ${ticket.status === 'Resolved' ? 'resolved' : ticket.status === 'Open' ? 'open' : 'progress'}">${statusLabel(ticket.status)}</span></div><div class="employee-meta">${escapeHTML(ticket.priority)} · ${formatDate(ticket.created_at)}</div><p>${escapeHTML(ticket.description)}</p><strong>${tr('updates')}</strong><ul>${ticket.events.map(event => `<li>${escapeHTML(eventLabel(event.event))} — ${formatDate(event.created_at)}${event.note ? `<p>${escapeHTML(event.note)}</p>` : ''}</li>`).join('')}</ul>${ticket.status === 'Resolved' ? `<button class="btn secondary reopen-ticket" data-ticket="${ticket.id}" type="button">${tr('reopen')}</button>` : ''}</article>`).join('');
}
async function loadTickets() {
  const data = await api('/api/employee/tickets');
  tickets = data.tickets;
  renderTickets();
}
async function initializePortal() {
  const session = await api('/api/session'); csrfToken = session.csrf_token;
  if (!session.user) { showPortal(false); return; }
  if (session.user.role !== 'employee') { location.href = '/'; return; }
  showPortal(true);
  const assets = await api('/api/employee/assets');
  $('#assetOptions').innerHTML = `<option value="">${tr('noAsset')}</option>` + assets.assets.map(asset => `<option value="${asset.id}">${escapeHTML(asset.asset_tag)} — ${escapeHTML(asset.name)}</option>`).join('');
  await loadTickets();
}
$('#languageButton').addEventListener('click', () => setLanguage(language === 'ar' ? 'en' : 'ar'));
$('#loginForm').addEventListener('submit', async event => {
  event.preventDefault(); $('#loginError').textContent = '';
  const form = event.currentTarget;
  try {
    const result = await api('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:form.elements.username.value,password:form.elements.password.value})});
    csrfToken = result.csrf_token; form.reset(); await initializePortal();
  } catch (error) { $('#loginError').textContent = translateError(error.message); }
});
$('#ticketForm').addEventListener('submit', async event => {
  event.preventDefault(); $('#ticketError').textContent = '';
  const form = event.currentTarget;
  const item = {title:form.elements.title.value.trim(),description:form.elements.description.value.trim(),asset_id:form.elements.asset_id.value ? Number(form.elements.asset_id.value) : null,category:form.elements.category.value,impact:2,urgency:2};
  try {
    const result = await api('/api/employee/tickets', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});
    form.reset(); $('#ticketError').textContent = `${tr('success')}: #${result.id}`; await loadTickets();
  } catch (error) { $('#ticketError').textContent = translateError(error.message); }
});
$('#logoutButton').addEventListener('click', async () => {
  try { await api('/api/logout', {method:'POST'}); } catch (_) { /* Expired sessions are already logged out. */ }
  csrfToken = ''; tickets = []; showPortal(false);
});
$('#ticketList').addEventListener('click', async event => {
  const button = event.target.closest('.reopen-ticket');
  if (!button) return;
  try { await api(`/api/employee/tickets/${button.dataset.ticket}/reopen`, {method:'POST'}); await loadTickets(); }
  catch (error) { $('#ticketError').textContent = translateError(error.message); }
});
setLanguage(language);
initializePortal().catch(() => showPortal(false));
