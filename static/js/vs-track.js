/* Voscene — แหล่งที่มาของ Lead + คลิก LINE/โทร (ของเว็บเราเอง ไม่ใช่ของแพลตฟอร์มโฆษณา)
 *
 * - เก็บใน sessionStorage ของแท็บเท่านั้น: ไม่มีคุกกี้ ไม่มีตัวระบุถาวร ปิดแท็บ = หาย
 * - ส่งขึ้นเซิร์ฟเวอร์ 2 ทางเท่านั้น: แนบไปกับฟอร์มตอนผู้ใช้กดส่งเอง (vsAttribution)
 *   และตอนคลิก LINE/โทร (ครั้งเดียวต่อ session ต่อประเภท)
 * - ทุกอย่างอยู่ใน try/catch — สคริปต์นี้พังต้องไม่ทำให้ฟอร์มพัง
 */
(function () {
  var ATTR = 'vs_attr', SID = 'vs_sid', FIELDS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
  var store = null;
  try { store = window.sessionStorage; store.getItem(ATTR); } catch (e) { store = null; }

  function read() { try { return JSON.parse(store.getItem(ATTR) || 'null'); } catch (e) { return null; } }
  function write(v) { try { store.setItem(ATTR, JSON.stringify(v)); } catch (e) { /* ignore */ } }
  function bare(h) { return (h || '').replace(/^www\./, ''); }

  // ---- จำแหล่งที่มาของการเข้าเว็บครั้งนี้ ----
  try {
    var params = new URLSearchParams(location.search), utm = {}, hasUtm = false;
    FIELDS.forEach(function (k) { var v = params.get(k); if (v) { utm[k] = v.slice(0, 128); hasUtm = true; } });
    var ref = document.referrer || '', external = false;
    try { external = !!ref && bare(new URL(ref).hostname) !== bare(location.hostname); } catch (e) { external = false; }
    var current = read();
    // มี UTM ใหม่ = มาจากลิงก์แคมเปญ ใช้ชุดนี้แทน · ไม่งั้นคงชุดแรกของ session ไว้
    if (hasUtm || !current) {
      utm.landing_page = (location.origin + location.pathname + location.search).slice(0, 500);
      utm.referrer = external ? ref.slice(0, 500) : '';
      write(utm);
    }
  } catch (e) { /* ignore */ }

  function sid() {
    try {
      var s = store.getItem(SID);
      if (!s) {
        s = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
          : (Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12));
        store.setItem(SID, s);
      }
      return s;
    } catch (e) { return ''; }
  }

  // ---- แนบแหล่งที่มา + เวลาที่ใช้กรอก ไปกับฟอร์ม ----
  document.addEventListener('focusin', function (e) {
    var f = e.target && e.target.form;
    if (f && !f.dataset.vsT0) f.dataset.vsT0 = String(Date.now());
  });

  window.vsAttribution = function (fd, form) {
    try {
      var a = read() || {};
      FIELDS.concat(['landing_page', 'referrer']).forEach(function (k) { if (a[k]) fd.set(k, a[k]); });
      if (form && form.dataset.vsT0) fd.set('form_ms', String(Date.now() - Number(form.dataset.vsT0)));
    } catch (e) { /* ignore */ }
    return fd;
  };

  // ---- คลิก LINE / โทร (ไม่ใช่ Lead — แค่รู้ว่ามีคนกด) ----
  function track(type) {
    try {
      if (window.dataLayer) window.dataLayer.push({ event: type });
      if (!store || store.getItem('vs_ev_' + type)) return; // นับแล้วใน session นี้
      var s = sid();
      if (!s) return;
      var a = read() || {};
      var body = JSON.stringify({
        event: type, sid: s, path: location.pathname,
        utm_source: a.utm_source || '', utm_medium: a.utm_medium || '',
        utm_campaign: a.utm_campaign || '', utm_content: a.utm_content || '', referrer: a.referrer || ''
      });
      var sent = navigator.sendBeacon
        ? navigator.sendBeacon('/api/event', new Blob([body], { type: 'application/json' }))
        : (fetch('/api/event', { method: 'POST', body: body, keepalive: true,
             headers: { 'Content-Type': 'application/json' } }), true);
      if (sent) store.setItem('vs_ev_' + type, '1');
    } catch (e) { /* ignore */ }
  }

  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (href.indexOf('tel:') === 0) track('phone_click');
    else if (/(^|\/\/)(line\.me|lin\.ee)\//i.test(href)) track('line_click');
  }, true);
})();
