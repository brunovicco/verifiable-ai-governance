# ADR 0020 — Consistência transacional e vigência das revisões de ativos

## Status

Aceito.

## Date

2026-08-01.

## Context

O inventário comparava `expected_version` somente depois de carregar modelos, agentes
e sistemas. Como o SQLAlchemy não emitia atualização condicional nem bloqueava as
linhas, dois comandos concorrentes podiam aceitar a mesma versão. Em particular, uma
revisão podia calcular o digest sobre um escopo enquanto outra transação alterava esse
mesmo ativo, produzindo uma projeção aprovada inconsistente.

Além disso, agentes migrados recebiam os marcadores `unversioned` e `unspecified`, mas
as regras aceitavam qualquer texto não vazio. Revisões vencidas mantinham o status
histórico `approved` sem expor uma vigência separada, o que podia induzir usuários e
futuros adapters a tratar uma decisão expirada como corrente.

## Decision

Todo comando mutável de inventário bloqueará primeiro a linha do `ai_system` com
`SELECT ... FOR UPDATE OF ai_systems`. Essa linha será o mutex transacional do
agregado. Alterações de sistema, criação, atualização, revisão e aposentadoria de
modelos ou agentes obedecerão à mesma ordem de lock antes de validar versão, owner,
dependências ou política.

O lock permanece até commit ou rollback. Assim, comandos sobre sistemas diferentes
continuam independentes, enquanto operações sobre o mesmo sistema são serializadas. O
segundo comando recarrega o agregado depois do lock e rejeita a versão obsoleta com
conflito estável.

O domínio rejeitará explicitamente os marcadores transitórios da migração. A vigência
será representada por `review_state`, calculado como `not_reviewed`, `current` ou
`expired` a partir de digest, deadline e relógio UTC. O status persistido não será
reescrito por passagem do tempo; API, portal e futuros pontos de enforcement devem usar
o estado calculado para decisões de vigência.

## Alternatives considered

- **`version_id_col` em todas as entidades:** ofereceria updates condicionais, mas
  ampliaria a mudança para workflows fora do inventário, que hoje incrementam versões
  explicitamente e precisariam de tratamento uniforme para `StaleDataError`.
- **Lock individual de cada modelo e agente:** permitiria mais concorrência, porém
  exigiria ordem global entre sistema, modelos e agentes e seria mais suscetível a
  deadlocks durante invalidações em cascata.
- **Job que altera `approved` para outro status no vencimento:** duplicaria um fato
  derivável, introduziria atraso operacional e misturaria lifecycle com vigência.
- **Aceitar os marcadores migrados com alerta:** foi rejeitado porque permitiria aprovar
  um escopo cuja versão ou região real continua desconhecida.

## Consequences

- comandos concorrentes no mesmo sistema executam sequencialmente;
- o throughput entre sistemas diferentes não é reduzido;
- versões esperadas tornam-se efetivas para todas as mutações do inventário;
- revisão de agente e alteração de modelo não podem atravessar a mesma janela crítica;
- consumidores precisam distinguir lifecycle `status` de `review_state`;
- registros migrados exigem atualização explícita antes de aprovação.

## Security and privacy impact

O lock impede aprovação sobre escopo obsoleto e preserva a ligação entre digest,
decisão e conteúdo corrente. Nenhum novo dado pessoal é persistido. O estado calculado
usa metadados já existentes e não registra consultas ou conteúdo de prompts. A rejeição
dos marcadores mantém comportamento fail-closed para provenance incompleta.

## Operational impact

Não há nova migração de banco. PostgreSQL precisa suportar row-level locking, já
garantido pela versão adotada. Transações de inventário devem permanecer curtas e não
executar chamadas externas enquanto seguram o lock. A CI passa a executar uma regressão
concorrente em PostgreSQL 17; o teste local é habilitado por
`POSTGRES_TEST_DATABASE_URL`.

Métricas futuras devem observar tempo de espera, conflitos de versão e duração das
transações por sistema, sem incluir identificadores sensíveis em labels.

## Follow-up

- usar `review_state=current` no adapter do `policy-model-router`;
- criar alertas para revisões próximas do vencimento;
- acompanhar contenção antes de considerar locks mais granulares;
- avaliar versionamento condicional uniforme quando outros agregados forem revisados.
