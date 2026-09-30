import { useEffect, useState } from 'react';
import { buildModel, metric, timeline, validSnapshot } from './model';

const time = value => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
const Badge = ({ state }) => <span className={`badge ${state?.toLowerCase()}`}><i />{state}</span>;
async function get(path, signal) {
  const response = await fetch(path, { signal, cache: 'no-store' });
  if (!response.ok) throw new Error('Endpoint unavailable');
  return response.json();
}
export default function App() {
  const [data, setData] = useState({ statusOk: false, targetsOk: false });
  const [now, setNow] = useState(Date.now());
  const [refresh, setRefresh] = useState(0);
  const [filter, setFilter] = useState('All events');
  useEffect(() => {
    let disposed = false, timer, controller;
    async function poll() {
      controller = new AbortController();
      const deadline = setTimeout(() => controller.abort(), 5000);
      const results = await Promise.allSettled(['/api/status', '/api/prometheus/targets', '/api/prometheus/resources'].map(path => get(path, controller.signal)));
      clearTimeout(deadline);
      if (disposed) return;
      const [status, targets, resources] = results;
      setData(previous => ({
        snapshot: status.status === 'fulfilled' && validSnapshot(status.value) ? status.value : previous.snapshot,
        statusOk: status.status === 'fulfilled' && !!validSnapshot(status.value),
        targets: targets.status === 'fulfilled' ? targets.value : null,
        targetsOk: targets.status === 'fulfilled',
        resources: resources.status === 'fulfilled' ? resources.value : null,
      }));
      timer = setTimeout(poll, 4000);
    }
    poll();
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); };
  }, [refresh]);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const model = buildModel(data.snapshot, data.statusOk, data.targets, data.targetsOk, now);
  const events = timeline(data.snapshot).filter(e => filter === 'All events' || (filter === 'Recoveries' ? e.event === 'RECOVERED' : e.event === 'ACTIVE'));
  const notifications = data.snapshot?.notifications || [];
  const lastNotification = notifications.at(-1);
  const cpu = metric(data.resources, 'healthcheck_process_cpu_percent', now);
  const memory = metric(data.resources, 'healthcheck_process_memory_bytes', now);
  return <div className="layout">
    <aside className="sidebar">
      <a className="brand" href="#overview"><img src="/favicon.svg" alt="" /><span>HEALTHCHECK<strong>SENTINEL</strong></span></a>
      <div className="nav-label">WORKSPACE</div>
      <nav><a href="#overview">◫ <span>Overview</span></a><a href="#services">▦ <span>Services</span></a><a href="#incidents">◷ <span>Incident history</span></a></nav>
      <div className="sidebar-bottom"><span className="local-dot" /> Local environment<p>Read-only monitoring console</p><small>HEALTHCHECK SENTINEL / 01</small></div>
    </aside>
    <main id="overview">
      <header><div><div className="eyebrow">OPERATIONS / LIVE MONITORING</div><h1>System overview<span>.</span></h1><p>Service health, dependency signals and incident activity.</p></div><div className="header-actions"><span className="read-only">READ ONLY</span><button onClick={() => setRefresh(v => v + 1)}>↻ Refresh</button></div></header>
      <section className={`summary ${model.overall.toLowerCase()}`} aria-label="Overall system status"><div className="summary-icon">{model.overall === 'HEALTHY' ? '✓' : '!'}</div><div><div className="eyebrow">OVERALL SYSTEM STATUS</div><h2>{model.overall === 'HEALTHY' ? 'All systems operational' : model.overall === 'UNKNOWN' ? 'Waiting for current signals' : 'System needs attention'}</h2><p>{model.healthyCount} of 7 components healthy · Refreshes every 4 seconds</p></div><Badge state={model.overall} /></section>
      {!model.available && <div className="notice" role="status">Current monitoring data is unavailable or older than 30 seconds. Service states are UNKNOWN; any incident history below is the last received snapshot.</div>}
      <section className="metrics" aria-label="System metrics">{[
        ['ACTIVE INCIDENTS', data.snapshot ? model.active.length : '—', 'In the latest snapshot'],
        ['RECOVERY EVENTS', data.snapshot ? model.recovered.length : '—', 'Resolved incidents retained'],
        ['AGENT CPU', cpu === null ? '—' : `${cpu.toFixed(2)}%`, 'Prometheus process metric'],
        ['AGENT MEMORY', memory === null ? '—' : `${(memory / 1048576).toFixed(1)} MB`, 'Resident process memory'],
      ].map(([label, value, detail]) => <div className="metric" key={label}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>)}</section>
      <section id="services"><div className="section-heading"><h2>Service health <span>07</span></h2><small>Last health check <b>{time(data.snapshot?.observed_at)}</b></small></div><div className="cards">{model.cards.map(card => <article className="card" key={card.id}><div className="card-top"><span className="component-icon">{card.kind === 'API SERVICE' ? '⌘' : card.icon === 'database' ? '▤' : card.icon === 'cache' ? '≋' : '⌁'}</span><Badge state={card.state} /></div><div className="eyebrow">{card.kind}</div><h3>{card.title}</h3>{card.kind === 'API SERVICE' ? <div className="probe-row"><span>/healthz <b>{card.healthz ?? '—'}</b></span><span>/readyz <b>{card.readyz ?? '—'}</b></span><span>{card.latency === null ? '—' : `${card.latency.toFixed(0)} ms`}</span></div> : <p className="card-detail">{card.detail}</p>}{card.inferred && <small className="inferred">Inferred from service dependency checks</small>}</article>)}</div></section>
      <div className="bottom-grid"><section id="incidents" className="panel"><div className="section-heading"><h2>Incident timeline</h2><span className="eyebrow">REAL EVENTS</span></div><div className="filters" aria-label="Filter timeline">{['All events', 'Incidents', 'Recoveries'].map(label => <button key={label} aria-pressed={filter === label} onClick={() => setFilter(label)}>{label}</button>)}</div><div className="timeline">{events.length ? events.slice(0, 20).map(event => <article className="event" key={`${event.incident_id}-${event.event}`}><span className={`event-dot ${event.event.toLowerCase()}`} /><div><div className="event-heading"><strong>{event.event === 'RECOVERED' ? 'Service recovery confirmed' : 'Incident detected'}</strong><Badge state={event.badge} /></div><p>{event.incident_id} · Root cause: {event.root_cause || 'Not attributed'}</p><small>{(event.affected_services || []).join(' · ')}</small><div className="event-meta"><time dateTime={event.at}>{new Date(event.at).toLocaleString()}</time><span>Slack: {event.receipt?.outcome || 'no receipt recorded'}</span></div></div></article>) : <div className="empty">No {filter === 'Recoveries' ? 'recovery events' : 'events'} in the current snapshot.</div>}</div></section>
      <section className="panel slack"><div className="section-heading"><h2>Slack notifications</h2><span className="slack-mark">#</span></div><div className="eyebrow">LATEST DELIVERY RECEIPT</div><h3 className={lastNotification?.outcome === 'delivered' ? 'success-text' : ''}>{lastNotification?.outcome === 'delivered' ? 'Delivered' : lastNotification?.outcome === 'failed' ? 'Delivery failed' : 'No receipt yet'}</h3><p>Actual notification transport results from the monitoring agent.</p><dl><div><dt>Incident</dt><dd>{lastNotification?.incident_id || '—'}</dd></div><div><dt>Event</dt><dd>{lastNotification?.status === 'RESOLVED' ? 'RECOVERED' : lastNotification?.status || '—'}</dd></div><div><dt>Last delivery attempt</dt><dd>{time(lastNotification?.completed_at)}</dd></div><div><dt>Delivered / failed</dt><dd>{notifications.filter(n => n.outcome === 'delivered').length} / {notifications.filter(n => n.outcome === 'failed').length}</dd></div></dl><div className="slack-note">Delivery receipts are historical evidence, not a live Slack connection check. No messages are sent from this dashboard.</div></section></div>
      <footer><span><span className="local-dot" /> Live sources: Sentinel status + Prometheus</span><span>Local time · {new Date(now).toLocaleTimeString()}</span></footer>
    </main>
  </div>;
}
