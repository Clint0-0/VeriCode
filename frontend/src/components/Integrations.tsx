import { Badge } from './ui'

function Row({ name, ok, value, missing }: { name: string; ok: boolean | null; value: string; missing?: string[] }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-700 py-2 first:border-0">
      <span className="text-sm text-slate-300">{name}</span>
      <span className="flex flex-wrap items-center gap-2">
        <Badge tone={ok === null ? 'gray' : ok ? 'green' : 'amber'}>{value}</Badge>
        {missing && missing.length > 0 && <span className="font-mono text-[11px] text-amber-300">missing: {missing.join(', ')}</span>}
      </span>
    </div>
  )
}

export function IntegrationStatus({ i }: { i: any }) {
  if (!i) return null
  const llm = i.llm
  return (
    <div>
      <Row name="LLM provider" ok={llm.ready && llm.real} value={llm.provider === 'mock' ? 'mock (scripted offline demo)' : `${llm.provider}${llm.ready ? '' : ' — not ready'}`} missing={llm.missing} />
      {llm.real && <Row name="Models (planner / coder)" ok={llm.ready} value={`${llm.planner_model || '—'} / ${llm.coder_model || '—'}`} />}
      <Row name="Tavily live search" ok={i.tavily.configured} value={i.tavily.configured ? 'configured' : 'not configured'} missing={i.tavily.missing} />
      <Row name="Execution sandbox" ok={i.sandbox.active === 'docker'} value={i.sandbox.active ? `${i.sandbox.active}${i.sandbox.active === 'process' ? (i.sandbox.process_network_isolation ? ' + no-network' : ' (network NOT restricted)') : ' (no network, ro rootfs)'}` : `error: ${i.sandbox.error}`} />
      <Row name="TypeScript compiler checker" ok={i.typescript_checker.available} value={i.typescript_checker.available ? 'available' : 'not installed (scripts/setup.sh)'} />
      <Row name="Authentication" ok={true} value={`session + CSRF · bound to ${i.auth.host}${i.auth.allow_remote ? ' (remote allowed)' : ''}`} />
      <Row name="Database schema" ok={null} value={`v${i.schema_version}`} />
    </div>
  )
}
