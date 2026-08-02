# ADR 0022 — Incidentes, kill switch e exceções temporárias

## Status

Aceito.

## Date

2026-08-02.

## Context

O backlog P1 previa "Incidentes, kill switch, exceções temporárias e plano de
remediação" como funcionalidade nativa da plataforma, não um wrapper de projeto
externo. Uma tabela `Incident` já existia no schema (criada pelo `create_all()` inicial
da migração 0001), com `title`, `severity`, `status`, `description`, `detected_at`,
`owner_id` e `containment`, mas sem domínio, aplicação, adapter, router ou schema —
estava preparada, não construída. `Agent.kill_switch_enabled` já tinha um significado
real, porém estreito: `review_agent_scope()` exige o campo `true` para aprovar o
escopo de um agente, mas nada no código executa essa parada em runtime.

O ADR 0002 já havia comprometido esta plataforma com um desenho específico para uma
futura "exceção": entidade própria, prazo, compensating controls e aprovação do
comitê, sem bypass direto do status. O RACI já definia "Gerir incidente" com Negócio
como accountable e Segurança/DevOps como executores, além da regra de segregação
"exceção não é aprovada pelo mesmo papel que solicita ou implementa a exceção". O
princípio de governança "contestabilidade e remediação quando houver impacto
material" também já estava declarado, sem modelo de dados correspondente.

## Decision

O domínio `domain/incidents.py` modela um ciclo de vida linear e explícito:
`open → contained → remediating → closed`, validado por um mapa de transições
permitidas. Encerrar um incidente exige um plano de remediação completo (responsável,
prazo e descrição) já registrado — a mesma disciplina de "não aceitar estado
incompleto" já usada em `review_model_scope`/`review_agent_scope`.

O kill switch em runtime é uma ação nova e distinta da declaração revisada: o agente
ganha `kill_switch_engaged`, `kill_switch_engaged_at` e `kill_switch_engaged_by`,
separados de `kill_switch_enabled`. Acionar o kill switch exige que o agente já tenha
declarado a capacidade na revisão de Segurança e que o incidente não esteja encerrado;
restaurar exige um acionamento vigente. Isso preserva o significado já existente de
`kill_switch_enabled` em vez de sobrepor um novo comportamento a ele.

Exceções temporárias (`PolicyException`) são sempre vinculadas a um incidente, com
`purpose`, `scope_description`, `compensating_controls` e `expires_at` obrigatórios —
os quatro elementos exigidos pelo ADR 0002 e pela linguagem de "finalidade, acesso,
retenção e aprovação explícitos" já usada para exceções de telemetria. O status
persistido (`pending`/`approved`/`rejected`/`revoked`) nunca é reescrito pela
passagem do tempo; a vigência (`pending`/`active`/`expired`/`rejected`/`revoked`) é
calculada em tempo de leitura comparando `expires_at` a `now`, no mesmo padrão de
`asset_review_state`. Decidir uma exceção exige `decided_by != requested_by` —
segregação de funções aplicada no domínio, não apenas documentada.

Toda mutação de incidente, kill switch ou exceção adquire o lock `SELECT ... FOR
UPDATE OF ai_systems` do sistema envolvido antes de validar versão ou estado, reusando
exatamente o mutex transacional por agregado já decidido no ADR 0020 — não um segundo
mecanismo de concorrência.

## Alternatives considered

- **Exceções de propósito geral, aplicáveis a qualquer iniciativa ou sistema sem
  incidente:** rejeitado nesta etapa porque o backlog agrupa exceções com
  incidentes/kill-switch/remediação, e todo precedente existente (ADR 0002, RACI) fala
  de compensar um risco durante um incidente, não de uma isenção permanente de
  política. Um motor de exceções geral que toque o policy engine e todos os gates é um
  trabalho maior e separado.
- **Novo papel de "comitê" para aprovar exceções:** rejeitado porque o único primitivo
  de papel além de owner/admin nesta base é `ApprovalArea`, ligado ao mapeamento de
  grupos OIDC do fluxo de gates da iniciativa. Criar um papel paralelo só para esta
  fatia seria desproporcional; a aprovação por administrador com segregação de funções
  obrigatória é a aproximação honesta mais próxima, registrada aqui como simplificação
  conhecida frente à linguagem "aprovação do comitê" do ADR 0002.
- **Autoridade de kill switch restrita a Segurança/DevOps:** rejeitado pelo mesmo
  motivo — reaproveita o limite "owner do sistema ou administrador" já usado em toda
  mutação de inventário, em vez de inventar um novo recorte de papel.
- **Persistir apenas o resultado final de cada tentativa, sem o registro `pending`
  inicial:** não se aplica a este desenho da mesma forma que ao roteamento de modelos,
  pois aqui não há chamada de rede externa entre a intenção e o resultado; a escrita é
  local e síncrona sob o mesmo lock.

## Consequences

- `Incident` ganha campos de remediação (`remediation_owner_id`,
  `remediation_description`, `remediation_due_at`, `resolved_at`) e passa a usar
  `Enum(RiskTier/IncidentStatus, native_enum=False)` em vez de `String` livre;
- `Agent` ganha três colunas novas de kill switch em runtime, sem alterar o
  significado de `kill_switch_enabled`;
- `PolicyException` é uma tabela nova, sempre vinculada a um incidente;
- decisões de exceção ficam restritas a administradores — uma simplificação a
  revisar se um modelo de autorização mais rico for adotado;
- nenhuma revisão de modelo ou agente existente é invalidada por esta migração (ao
  contrário da 0008): os campos novos são aditivos e opcionais.

## Security and privacy impact

Nenhum conteúdo de prompt, documento ou execução é registrado; incidentes e exceções
carregam apenas metadados estruturados (título, severidade, descrição textual
fornecida por humanos, prazos). A trilha de auditoria hash-encadeada registra cada
transição (`incident.reported`, `incident.contained`,
`incident.remediation_plan_set`, `incident.closed`, `incident.kill_switch_engaged`,
`incident.kill_switch_restored`, `incident.exception_requested`,
`incident.exception_decided`, `incident.exception_revoked`) com ator, entidade e
versão, sem duplicar o corpo da solicitação. A segregação de funções da exceção é
recusada no domínio, não apenas na borda HTTP, então nenhum adapter futuro pode
contornar a regra sem também contornar o teste de arquitetura.

## Operational impact

A migração 0009 é somente aditiva: novas colunas nulas em `incidents` e `agents`,
mais a tabela `policy_exceptions`. Não há reprocessamento de dados existentes nem
invalidação de aprovações. A funcionalidade é sempre ativa — diferente das integrações
opt-in como `policy-model-router`, incidentes fazem parte do núcleo do produto e não
têm flag de habilitação.

O portal expõe reportar, conter, planejar remediação, encerrar, acionar/restaurar
kill switch e solicitar exceção. Decidir e revogar exceção são endpoints
administrador-somente e não têm tela no portal nesta entrega, seguindo o mesmo padrão
já usado para outras ações administrador-somente da plataforma (bloqueio/restauração
de acesso emergencial, invalidação de cache de autorização), que também não têm UI.

## Follow-up

- adicionar tela administrador para decidir e revogar exceções quando o portal tiver
  um conceito de identidade administrativa local;
- avaliar um papel de aprovação mais rico que substitua a simplificação
  administrador-como-comitê;
- alertar antecipadamente prazos de remediação próximos do vencimento, no mesmo
  espírito do follow-up já registrado nos ADR 0019/0020 para revisões de escopo;
- considerar referenciar esta funcionalidade a partir do controle `GOV-AGT-001` do
  catálogo, hoje limitado a exigir kill switch documentado;
- cobrir com teste os caminhos 403/404 de `get_incident`/`list_incidents` para
  sistemas inexistentes de forma mais exaustiva, hoje exercitados apenas pelo caminho
  feliz e pelo caso de autorização.
