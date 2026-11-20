'use strict';
(() => {
  const storageKey = 'crossfraud-static-reviews-v1';
  let snapshot;
  function state() {
    const raw = localStorage.getItem(storageKey);
    return raw ? JSON.parse(raw) : {};
  }
  function load() {
    snapshot ??= fetch('/demo.json').then(response => {
      if (!response.ok) throw new Error('Synthetic demo data is unavailable.');
      return response.json();
    }).catch(error => { snapshot = undefined; throw error; });
    return snapshot;
  }
  function merge(alert, entry = {}) {
    const history = entry.history || [];
    return {...alert, review_history:history, review_outcome:history.at(-1)?.outcome || 'unresolved'};
  }
  window.crossfraudDemo = async (path, body) => {
    const data = await load();
    const url = new URL(path, location.origin);
    const parts = url.pathname.split('/');
    if (url.pathname === '/catalog') return data.catalog;
    if (url.pathname === '/alerts') {
      const saved = state();
      return {source:'synthetic', review_only:true, alerts:data.alerts.map(alert => merge(alert, saved[alert.alert_id]))};
    }
    if (parts[1] === 'conversations') {
      const chat = data.conversations[decodeURIComponent(parts[2])];
      if (!chat) throw new Error('Conversation unavailable.');
      const cutoff = url.searchParams.get('cutoff');
      return cutoff ? {...chat,messages:chat.messages.filter(message => message.time <= cutoff)} : chat;
    }
    const id = decodeURIComponent(parts[2] || '');
    const alert = data.alerts.find(item => item.alert_id === id);
    if (!alert) throw new Error('Alert unavailable.');
    const saved = state();
    const entry = saved[id] ??= {history:[],notes:[]};
    if (body === undefined) return parts[3] === 'notes' ? entry.notes : merge(alert, entry);
    const stamp = new Date().toISOString();
    if (parts[3] === 'review' && ['confirmed','dismissed','unresolved'].includes(body.outcome)) {
      entry.history.push({outcome:body.outcome,recorded_at_utc:stamp});
    } else if (parts[3] === 'notes' && typeof body.note === 'string' && body.note.trim().length && body.note.trim().length <= 1000) {
      entry.notes.push({note:body.note.trim(),recorded_at_utc:stamp});
    } else {
      throw new Error('Invalid note or review outcome.');
    }
    localStorage.setItem(storageKey, JSON.stringify(saved));
    return parts[3] === 'notes' ? entry.notes : merge(alert, entry);
  };
})();
