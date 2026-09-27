/* Voscene — แหล่งที่มาของ Lead + คลิก LINE/โทร (ของเว็บเราเอง ไม่ใช่ของแพลตฟอร์มโฆษณา)
 *
 * - เก็บใน sessionStorage ของแท็บเท่านั้น: ไม่มีคุกกี้ ไม่มีตัวระบุถาวร ปิดแท็บ = หาย
 * - ส่งขึ้นเซิร์ฟเวอร์ 2 ทางเท่านั้น: แนบไปกับฟอร์มตอนผู้ใช้กดส่งเอง (vsAttribution)
 *   และตอนคลิก LINE/โทร (ครั้งเดียวต่อ session ต่อประเภท)
 * - คลิก LINE/โทรครั้งแรกของ session ส่งต่อให้ window.trackLead → GA4 generate_lead / Meta Lead
 *   (เฉพาะผู้ชมที่กดยอมรับคุกกี้แล้ว — ไม่งั้น gtag/fbq ไม่มีอยู่ในหน้า)
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
      // ส่งเป็น conversion ให้ GA4/Meta ด้วย (ครั้งเดียวต่อ session เหมือนรายงานของเรา)
      // trackLead ใน base.html ไม่ส่งอะไรถ้าผู้ชมยังไม่กดยอมรับคุกกี้ — gtag/fbq ยังไม่ถูกโหลด
      if (typeof window.trackLead === 'function') window.trackLead(type === 'line_click' ? 'line' : 'phone');
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

  // ---- รหัสอ้างอิงในข้อความ LINE ----
  // เว็บไม่มีฟอร์มแล้ว แหล่งที่มาจะหายตรงจุดที่ลูกค้ากด LINE จึงพิมพ์รหัสสั้น ๆ ไว้ในข้อความแรกให้
  // ทีมคัดลอกไปวางใน "+ เพิ่ม Lead" (marketing_core.parse_chat_ref อ่านรูปแบบเดียวกันนี้)
  //   แคมเปญ/source.medium[/content]  ·  ไม่มี UTM = web หรือ web/โฮสต์ที่พามา
  function slug(v) { return String(v || '').toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60); }
  function chatRef() {
    var a = read() || {};
    if (a.utm_source || a.utm_campaign) {
      var ref = (slug(a.utm_campaign) || '-') + '/' + slug(a.utm_source) + '.' + slug(a.utm_medium);
      return a.utm_content ? ref + '/' + slug(a.utm_content) : ref;
    }
    try { if (a.referrer) return 'web/' + bare(new URL(a.referrer).hostname); } catch (e) { /* ignore */ }
    return 'web';
  }
  function lineMessageUrl(href) {
    // เฉพาะลิงก์ที่รู้ LINE ID (…/ti/p/@ID) — lin.ee ย่อไม่มี ID ให้ใช้ลิงก์เดิม
    var m = /line\.me\/R\/ti\/p\/(@[A-Za-z0-9._-]+)/i.exec(href);
    if (!m) return '';
    var text = 'สวัสดีครับ สนใจระบบ Voscene\n(รหัสอ้างอิง: ' + chatRef() + ')';
    return 'https://line.me/R/oaMessage/' + encodeURIComponent(m[1]) + '/?' + encodeURIComponent(text);
  }
  window.vsChatRef = chatRef;

  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (href.indexOf('tel:') === 0) track('phone_click');
    else if (/(^|\/\/)(line\.me|lin\.ee)\//i.test(href)) {
      track('line_click');
      try {
        var withRef = lineMessageUrl(href);
        if (withRef) a.setAttribute('href', withRef); // เปลี่ยนก่อนเบราว์เซอร์เปิดลิงก์ (capture phase)
      } catch (err) { /* ใช้ลิงก์เดิม */ }
    }
  }, true);
})();
