export interface ToolDef {
  name: string
  displayName: string
  description: string
  enabledByDefault: boolean
}

export const TOOL_COLORS: Record<string, string> = {
  sql:     'text-yellow-400 border-yellow-400/30 bg-yellow-400/10',
  rag:     'text-emerald-400 border-emerald-400/30 bg-emerald-400/10',
  jobpred: 'text-violet-400 border-violet-400/30 bg-violet-400/10',
  syslog:  'text-sky-400 border-sky-400/30 bg-sky-400/10',
}

export const TOOL_LABELS: Record<string, string> = {
  query_hpc_database:    'HPC Telemetry Analytics',
  search_hpc_docs:       'Doc Search',
  predict_job_stats:     'Job Prediction',
  lookup_syslog_event:   'Syslog Lookup',
  explain_syslog_event:  'Syslog Cascade',
  syslog_recent_activity:'Syslog Activity',
  query_syslog_history:  'Syslog History',
  syslog_graph_stats:    'Syslog Graph Stats',
}

/** Map tool function name → registry name (for coloring). */
export const TOOL_REGISTRY_NAME: Record<string, string> = {
  query_hpc_database:    'sql',
  search_hpc_docs:       'rag',
  predict_job_stats:     'jobpred',
  lookup_syslog_event:   'syslog',
  explain_syslog_event:  'syslog',
  syslog_recent_activity:'syslog',
  query_syslog_history:  'syslog',
  syslog_graph_stats:    'syslog',
}

export async function fetchTools(): Promise<ToolDef[]> {
  const res = await fetch('/api/tools')
  if (!res.ok) return []
  const data = await res.json()
  return data.tools as ToolDef[]
}
