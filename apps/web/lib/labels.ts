const LABELS: Record<string, string> = {
  draft: "Rascunho",
  under_review: "Em avaliação",
  approved: "Aprovada",
  active: "Ativo",
  suspended: "Suspenso",
  retired: "Aposentado",
  rejected: "Rejeitada",
  not_required: "Não aplicável",
  pending: "Pendente",
  not_started: "Não iniciado",
  low: "Baixo",
  medium: "Médio",
  high: "Alto",
  critical: "Crítico",
  business: "Negócio",
  architecture: "Arquitetura",
  security: "Segurança",
  infrastructure: "Infraestrutura",
  devops: "DevOps",
  privacy: "Privacidade",
  legal: "Jurídico",
  compliance: "Compliance",
  data: "Dados",
  a0_information: "Apenas informação",
  a1_recommendation: "Recomenda ações",
  a2_prepare_for_approval: "Prepara para aprovação",
  a3_reversible_actions: "Executa ações reversíveis",
  a4_high_impact_actions: "Executa ações de alto impacto",
  a5_high_autonomy: "Alta autonomia",
  "ai-system-card": "Ficha do sistema de IA",
  "ai-impact-assessment": "Avaliação de impacto de IA",
  ripd: "RIPD",
  "international-processing-assessment": "Análise de processamento internacional",
  "agent-card": "Ficha do agente",
  "human-oversight-plan": "Plano de supervisão humana",
  "threat-model": "Modelo de ameaças",
  "monitoring-plan": "Plano de monitoramento",
};

export function label(value: string): string {
  return LABELS[value] ?? value.replaceAll("_", " ");
}

export function statusClass(value: string): string {
  return `status status-${value.replaceAll("_", "-")}`;
}
