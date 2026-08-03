# ADR 0023 — Dashboard operacional

## Status

Aceito.

## Date

2026-08-02.

## Context

O backlog P1 pedia um "Dashboard de violações, blocked actions, drift, custo e
revisões vencidas." Antes de desenhar a agregação, verificamos exatamente quais desses
cinco nomes já têm dado real persistido nesta plataforma:

- **Blocked actions**: real — `ModelRoutingDecisionEntry.outcome`/`.reason_code`
  (feature de roteamento de modelos, ADR 0021) já persiste cada tentativa.
- **Revisões vencidas**: real — `ReviewableAssetMixin.review_state` já computa
  `not_reviewed`/`current`/`expired` em tempo de leitura via `asset_review_state()`
  (ADR 0019/0020).
- **Incidentes com remediação vencida** e **exceções ativas**: reais — adicionados
  pela feature de incidentes (ADR 0022).
- **Custo**: só existem *limites* declarados (`Agent.max_cost`,
  `ModelRoutingDecisionEntry.max_cost_usd`), nunca gasto real observado. Nenhuma
  tabela de gasto existe.
- **Drift**: nenhum dado persistido em lugar nenhum do código. Aparece apenas como
  cabeçalho de coluna em `packages/document-templates/templates/monitoring-plan.md`
  e como prosa em `docs/governance/MONITORING.md`/`STAGE_GATES.md`. Depende da
  integração ainda não construída com `ragforge` (avaliações e regressões).

Um produto de governança e assurance não pode fabricar evidência. A decisão de
desenho segue diretamente dessa restrição.

`GET /api/v1/systems` (`routers/inventory.py`) já lista todos os sistemas de IA da
plataforma exigindo apenas `CurrentPrincipal` — nenhuma checagem de ownership. Isso já
estabelece que leituras de portfólio, não restritas a um dono, são um padrão de
autorização existente nesta base, não algo novo a inventar.

## Decision

Um único endpoint, `GET /api/v1/dashboard`, agrega quatro fontes reais e expõe a
quinta (drift) como indisponível de forma explícita — nunca omitida silenciosamente
nem fabricada. A autorização reusa exatamente o padrão de `GET /api/v1/systems`:
qualquer principal autenticado, sem checagem de ownership, porque supervisão de
portfólio é o propósito do recurso.

"Custo" é mostrado como bloqueios por limite de custo
(`reason_code=cost_limit_exceeded` nas decisões de roteamento), nunca como gasto —
a única leitura honesta possível hoje.

Vigência de revisão e de exceção são recomputadas em Python a partir das mesmas
funções puras já usadas em todo o resto do produto (`asset_review_state()`,
`evaluate_exception_state()`), não reimplementadas em SQL bruto. O adapter
(`adapters/dashboard_persistence.py`) devolve apenas fatos crus
(`approved_scope_digest`, `next_review_at`, `risk_tier` / `status`, `expires_at`); o
caso de uso (`application/dashboard.py::BuildDashboardSnapshot`) aplica a mesma regra
de negócio já testada em vez de mantê-la em dois lugares que poderiam divergir (por
exemplo, se `MAX_REVIEW_INTERVAL` mudar no futuro). Contagens de status de incidente e
de outcome de roteamento, por serem campos diretamente persistidos sem regra
computada, são agregadas com `GROUP BY` normal.

Nenhuma migração de banco é necessária: o dashboard é uma leitura agregada sobre
tabelas que já existem por causa das features de roteamento (ADR 0021) e incidentes
(ADR 0022).

## Alternatives considered

- **Computar vigência de revisão/exceção em SQL bruto para performance:** rejeitado
  — duplicaria uma regra de negócio já existente em domínio puro, com risco real de
  divergência silenciosa entre a versão SQL e a versão Python se a regra mudar.
- **Fabricar um número de "drift" a partir de um proxy (por exemplo, contagem de
  invalidações de revisão):** rejeitado — invalidação de revisão mede outra coisa
  (mudança de escopo), e apresentá-la como "drift" enganaria quem lê o painel. Um
  produto de assurance não pode inventar evidência.
- **Restringir o dashboard ao escopo do owner, como a maioria dos outros
  endpoints:** rejeitado — o propósito de um dashboard operacional é justamente a
  visão de portfólio; restringi-lo por ownership o esvaziaria. O precedente de
  `GET /api/v1/systems` já mostra que essa exceção é aceita nesta base.
- **Métricas com janela de tempo (por exemplo, "últimos 30 dias"):** adiado para uma
  entrega futura; a v1 é um retrato all-time, mais simples de implementar e validar
  corretamente primeiro.

## Consequences

- nenhuma nova migração, nenhuma nova dependência de frontend (sem biblioteca de
  gráficos — o painel usa os mesmos `panel`/tabelas já usados em todo o portal);
- vigência de revisão e de exceção são recomputadas a cada requisição sobre todas as
  linhas da plataforma; aceitável na escala atual, deve ser revisitado (paginação ou
  cache) se o número de modelos/agentes/exceções crescer significativamente;
- "drift" permanece um placeholder explícito até a integração com `ragforge`;
- o painel não tem cache: cada carregamento reflete o estado corrente, coerente com o
  princípio de nunca apresentar um estado obsoleto como atual.

## Security and privacy impact

A resposta contém apenas contagens agregadas — nenhum identificador de usuário
final, conteúdo de prompt ou documento, nem detalhe por sistema além do necessário
para o agrupamento por risco. A autorização "qualquer autenticado" é a mesma já usada
para listar sistemas; nenhum novo limite de exposição é introduzido.

## Operational impact

Sem migração. A funcionalidade é sempre ativa, sem flag de habilitação, assim como as
features de incidentes e roteamento que a alimentam.

## Follow-up

- adicionar drift quando a integração com `ragforge` existir;
- considerar métricas com janela de tempo além do retrato all-time atual;
- considerar paginação ou cache se o número de linhas agregadas crescer;
- ligar os números do painel a visões filtradas (por exemplo, clicar em "remediações
  vencidas" deveria levar à lista desses incidentes).
