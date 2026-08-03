# ADR 0024 - Métricas executivas do dashboard operacional

## Status

Aceito.

## Date

2026-08-03.

## Context

O backlog P2 pedia "Métricas executivas de cobertura, SLA, risco residual e
efetividade de controles," estendendo o dashboard operacional recém-entregue
(ADR 0023). A mesma disciplina de honestidade se aplica: mostrar apenas o que é real.

- **Risco residual**: real, mas não onde o nome sugeria. `Assessment` não tem uma
  coluna própria `residual_risk` - o valor informado pelo owner na resposta
  estruturada (`AIImpactAnswers.residual_risk` etc., em `domain/assessments.py`) já é
  persistido em `Assessment.risk_tier` no momento da submissão
  (`application/assessments.py`). Reusar essa coluna evita um erro de mapeamento
  fácil de cometer (confirmado durante a implementação: `mypy` rejeitou a tentativa
  inicial de ler uma coluna `residual_risk` inexistente).
- **SLA**: nenhum prazo-alvo declarado existe em lugar nenhum do código - só duração
  observada. `ReviewSubmission.submitted_at`/`.resolved_at` e
  `Incident.detected_at`/`.resolved_at` (ambos já presentes) dão tempo de ciclo real.
  Sem meta para comparar, a métrica é "tempo médio observado," nunca "% dentro do
  SLA" - a mesma escolha já feita para "custo" no ADR 0023.
- **Cobertura**: `Initiative.required_documents` e `domain/assessments.py::
  AssessmentKind` usam exatamente os mesmos valores de string
  (`"ai-impact-assessment"`, `"ripd"`, `"international-processing-assessment"`),
  confirmado lendo as duas definições. Isso torna a interseção confiável sem
  correspondência textual frágil.
- **Efetividade de controles**: nenhum dado existe. `ControlEvaluation` só registra
  aplicabilidade estática (`applicable: bool` + `reasons`), nunca se a evidência
  exigida foi de fato verificada ou se o controle preveniu algo.

## Decision

As três métricas reais estendem o mesmo `DashboardSnapshot`/`GET /api/v1/dashboard`
do ADR 0023 - nenhum endpoint novo, nenhuma migração (todo campo usado já existe).

Risco residual é agregado por `RiskTier` a partir de `Assessment.risk_tier` entre
avaliações não-rascunho. Cobertura intersecta `required_documents` de cada iniciativa
não-rascunho com os três valores conhecidos de `AssessmentKind`, contando quantos têm
uma `Assessment` não-rascunho correspondente - deliberadamente limitado às três
avaliações estruturadas, não aos demais itens de `required_documents` que são
baseados em evidência (`ai-system-card`, `threat-model` etc.); cobrir esses exigiria
correspondência heurística contra o texto livre de `Evidence.kind`, uma computação
mais frágil, registrada como follow-up em vez de feita de forma pouco confiável.
Tempo de ciclo é a média de horas observadas entre submissão e resolução de rodadas
de revisão, e entre detecção e encerramento de incidentes; quando a amostra é vazia,
o resultado é `None` (não `0`), e o tamanho da amostra sempre acompanha a média para
que quem lê o painel possa julgar a confiabilidade de uma média com poucas
observações. Efetividade de controles recebe o mesmo tratamento de placeholder
explícito que "drift" no ADR 0023 (`control_effectiveness_available: false`).

## Alternatives considered

- **Definir cobertura contra todos os itens de `required_documents`, incluindo os
  baseados em evidência:** rejeitado por exigir correspondência heurística de texto
  livre contra `Evidence.kind`, com risco real de contagem incorreta silenciosa.
- **Expor "% dentro do prazo" para tempo de ciclo:** rejeitado - não há prazo-alvo
  declarado nesta plataforma para calcular conformidade contra ele.
- **Fabricar efetividade de controles a partir de um proxy (por exemplo, ausência de
  incidentes em sistemas com o controle aplicável):** rejeitado - ausência de
  incidente não prova que um controle funcionou, e apresentá-la como "efetividade"
  enganaria quem lê o painel.

## Consequences

- nenhuma migração, nenhum endpoint novo - extensão pura do `DashboardSnapshot`;
- cobertura de avaliações estruturadas fica deliberadamente mais estreita que o
  conjunto completo de `required_documents`;
- tempo de ciclo pode ter amostra pequena ou vazia no início da vida de um portfólio;
  o painel mostra o tamanho da amostra para não sugerir confiança indevida.

## Security and privacy impact

Mesma superfície do ADR 0023: apenas contagens e médias agregadas, nenhum
identificador de usuário final, conteúdo de prompt ou documento.

## Operational impact

Sem migração, sem flag de habilitação - a extensão é sempre ativa junto do endpoint
existente.

## Follow-up

- cobrir cobertura de `required_documents` baseados em evidência quando houver uma
  forma confiável de vincular `Evidence.kind` a cada item;
- efetividade de controles quando existir alguma verificação real de evidência por
  controle, não apenas aplicabilidade declarativa;
- considerar declarar metas de SLA explícitas nesta plataforma, o que permitiria uma
  métrica honesta de conformidade.
