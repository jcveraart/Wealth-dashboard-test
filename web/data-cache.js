'use strict';
/* Session-only data cache: no financial payloads are written to browser storage. */
const DATA_CACHE = new Map();
let DATA_EPOCH = 0;
async function cachedJSON(url, {ttl = 60000, force = false} = {}) {
  const old = DATA_CACHE.get(url), now = Date.now();
  if (old?.pending) return old.pending;
  if (!force && old?.value !== undefined && now - old.at < ttl) return old.value;
  const epoch = DATA_EPOCH;
  const entry = old || {};
  const pending = fetch(url, {cache: 'no-store'}).then(async response => {
    const value = await response.json();
    if (!response.ok || value?.error) throw Error(value?.error || 'Could not load this view.');
    if (epoch === DATA_EPOCH) DATA_CACHE.set(url, {value, at: Date.now()});
    return value;
  }).catch(error => { if (DATA_CACHE.get(url)?.pending === pending) DATA_CACHE.delete(url); throw error; });
  DATA_CACHE.set(url, {...entry, pending});
  return pending;
}
function invalidateData() { DATA_EPOCH++; DATA_CACHE.clear(); }
const cachedData = url => DATA_CACHE.get(url)?.value;
