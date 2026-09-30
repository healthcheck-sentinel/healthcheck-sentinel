export const FRESH_MS = 30000;
export const SERVICES = [
  { id: 'order-service', title: 'Order Service', kind: 'API SERVICE', icon: 'orders' },
  { id: 'payment-service', title: 'Payment Service', kind: 'API SERVICE', icon: 'payment' },
  { id: 'user-service', title: 'User Service', kind: 'API SERVICE', icon: 'users' },
];
export function timestamp(value) { const n = Date.parse(value); return Number.isFinite(n) ? n : null; }
export function fresh(value, now = Date.now()) {
  const at = timestamp(value); return at !== null && now - at >= -5000 && now - at < FRESH_MS;
}
export function number(value) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null; }
export function validSnapshot(data) {
  return data && timestamp(data.observed_at) !== null && data.services &&
    SERVICES.every(s => data.services[s.id] && typeof data.services[s.id].state === 'string') &&
    Array.isArray(data.incidents) && Array.isArray(data.notifications);
}
export function dependencyStatus(services, dependency, available, now = Date.now()) {
  if (!available) return { state: 'UNKNOWN', detail: 'Waiting for fresh dependency probes' };
  const results = ['order-service', 'payment-service'].map(name => services?.[name]?.evidence)
    .filter(e => e && fresh(e.timestamp, now) && e.healthz_status !== null)
    .map(e => e.dependencies?.[dependency]).filter(v => typeof v === 'boolean');
  if (!results.length) return { state: 'UNKNOWN', detail: 'No current dependency evidence' };
  const failures = results.filter(v => !v).length;
  return { state: failures === results.length ? 'DOWN' : failures ? 'DEGRADED' : 'HEALTHY',
    detail: `${results.length - failures}/${results.length} dependency probes passing` };
}
export function buildModel(snapshot, statusOk, targets, targetsOk, now = Date.now()) {
  const available = statusOk && validSnapshot(snapshot) && fresh(snapshot.observed_at, now);
  const services = SERVICES.map(meta => {
    const source = snapshot?.services?.[meta.id];
    const current = available && fresh(source?.evidence?.timestamp, now);
    const state = current && ['HEALTHY', 'DEGRADED', 'ZOMBIE', 'DOWN'].includes(source.state) ? source.state : 'UNKNOWN';
    return { ...meta, state, latency: current ? number(source?.evidence?.latency_ms) : null,
      checkedAt: source?.evidence?.timestamp, healthz: current ? source.evidence.healthz_status : null,
      readyz: current ? source.evidence.readyz_status : null };
  });
  const postgres = dependencyStatus(snapshot?.services, 'postgres', available, now);
  const redis = dependencyStatus(snapshot?.services, 'redis', available, now);
  const validTargets = targetsOk && targets?.status === 'success' && Array.isArray(targets?.data?.activeTargets);
  const monitoredTargets = validTargets ? targets.data.activeTargets.filter(t => ['prometheus', 'monitoring-agent'].includes(t.labels?.job)) : [];
  const self = monitoredTargets.find(t => t.labels?.job === 'prometheus');
  const promFresh = validTargets && self && fresh(self.lastScrape, now);
  const prometheus = !promFresh ? 'UNKNOWN' : self.health !== 'up' ? 'DOWN' :
    monitoredTargets.length < 2 || monitoredTargets.some(t => t.health !== 'up' || !fresh(t.lastScrape, now)) ? 'DEGRADED' : 'HEALTHY';
  const cards = [...services,
    { id: 'postgres', title: 'PostgreSQL', kind: 'DATABASE', icon: 'database', ...postgres, inferred: true },
    { id: 'redis', title: 'Redis', kind: 'CACHE', icon: 'cache', ...redis, inferred: true },
    { id: 'agent', title: 'Monitoring Agent', kind: 'OBSERVABILITY', icon: 'pulse', state: available ? 'HEALTHY' : 'UNKNOWN', detail: available ? 'Publishing fresh probe results' : 'Status endpoint unavailable or stale' },
    { id: 'prometheus', title: 'Prometheus', kind: 'OBSERVABILITY', icon: 'chart', state: prometheus, detail: promFresh ? `${monitoredTargets.filter(t => t.health === 'up').length}/${monitoredTargets.length} scrape targets up` : 'Scrape status unavailable or stale' },
  ];
  const overall = cards.some(c => c.state === 'DOWN') ? 'DOWN' : cards.some(c => ['ZOMBIE','DEGRADED'].includes(c.state)) ? 'DEGRADED' : cards.some(c => c.state === 'UNKNOWN') ? 'UNKNOWN' : 'HEALTHY';
  const incidents = Array.isArray(snapshot?.incidents) ? snapshot.incidents : [];
  return { available, services, cards, overall, active: incidents.filter(i => i.status === 'ACTIVE'),
    recovered: incidents.filter(i => i.status === 'RESOLVED'), healthyCount: cards.filter(c => c.state === 'HEALTHY').length };
}
export function receipt(notifications, id, status) {
  return [...(notifications || [])].reverse().find(n => n.incident_id === id && n.status === status);
}
export function timeline(snapshot) {
  const events = [];
  for (const incident of snapshot?.incidents || []) {
    const at = incident.confirmation_time || incident.first_failure_time;
    if (timestamp(at) !== null) events.push({ ...incident, at, event: 'ACTIVE', badge: incident.state, receipt: receipt(snapshot.notifications, incident.incident_id, 'ACTIVE') });
    if (incident.status === 'RESOLVED' && timestamp(incident.recovery_time) !== null)
      events.push({ ...incident, at: incident.recovery_time, event: 'RECOVERED', badge: 'RECOVERED', receipt: receipt(snapshot.notifications, incident.incident_id, 'RESOLVED') });
  }
  return events.sort((a,b) => timestamp(b.at) - timestamp(a.at));
}
export function metric(resources, name, now = Date.now()) {
  const item = resources?.status === 'success' && resources.data?.result?.find(r => r.metric?.__name__ === name);
  if (!item || !Array.isArray(item.value) || !Number.isFinite(Number(item.value[0])) || now - item.value[0]*1000 >= FRESH_MS || now < item.value[0]*1000 - 5000 || item.value[1] === '') return null;
  const v = Number(item.value[1]); return Number.isFinite(v) && v >= 0 ? v : null;
}
