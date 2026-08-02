# ADR 0021 — Enforcement em runtime de decisões do policy-model-router

## Status

Aceito.

## Date

2026-08-02.

## Context

O ADR 0019 revisa o escopo de modelos e agentes, mas não decide qual grupo lógico de
modelo uma execução concreta deve usar. O ADR 0019 e o ADR 0020 já listavam, como
follow-up, integrar essas revisões a um decisor de roteamento em runtime. Sem essa
integração, nada impede que um workflow invoque um modelo fora do escopo revisado, e
nada vincula a escolha de um roteador externo a uma revisão de Arquitetura vigente.

O `policy-model-router` é um serviço externo, independente desta plataforma, que recebe
metadados operacionais de uma tarefa (workload, risco, classe de dado, limites de custo
e latência) e devolve um grupo lógico de modelo ou uma rejeição explícita. Ele não tem
acesso a prompts, documentos ou identidade de usuário final, e não conhece o estado de
revisão dos ativos desta plataforma. Confiar apenas na resposta do roteador permitiria
que um serviço externo expandisse silenciosamente o escopo aprovado; confiar apenas na
revisão local, sem consultar o roteador, não atenderia ao objetivo de decidir em runtime
qual grupo usar entre os já aprovados.

## Decision

A aplicação manterá duas autoridades deliberadamente separadas. A governança local
(`evaluate_routing_scope`) decide **se** um agente pode operar e **quais grupos lógicos
revisados** estão elegíveis, antes de qualquer chamada externa: sistema operacional,
agente aprovado com revisão vigente, ao menos um modelo elegível (aprovado, com revisão
vigente e `routing_group` explícito, nunca o marcador de migração `unassigned`), classe
de dado autorizada por algum modelo elegível e custo dentro do limite revisado do
agente. O `policy-model-router` decide **qual** desses grupos elegíveis usar para um
`workflow_id`/`task_id` específico.

Cada tentativa é persistida como `pending` antes da chamada externa e finalizada como
`allowed`, `blocked` ou `dependency_unavailable` depois dela, em duas transações
distintas (persistir a intenção, depois persistir o resultado). Uma falha entre essas
duas transações ainda deixa evidência auditável do que foi tentado. O digest SHA-256 do
escopo (mesma receita de canonicalização já usada pelo digest de revisão do ADR 0004)
é capturado no momento da checagem local e revalidado contra uma leitura fresca do
registro depois da resposta externa; uma divergência bloqueia a decisão como
`registry_scope_changed` em vez de aceitar fatos potencialmente obsoletos.

A chamada ao roteador é um único `POST /route`, sem retry: a operação não é idempotente,
e repeti-la poderia produzir decisões duplicadas ou custos duplicados. Qualquer falha de
transporte, resposta malformada, resposta que não corresponda ao `workflow_id`/`task_id`
enviado, resposta acima do tamanho máximo configurado ou ausência de credencial
configurada para o agente é mapeada para o erro tipado `ModelRouterUnavailable` e
finalizada como `dependency_unavailable`, traduzido para HTTP 503 pela categoria já
existente `ErrorKind.DEPENDENCY_UNAVAILABLE`. Uma rejeição explícita do roteador
(`outcome=rejected`) é propagada como bloqueio com o `reason_code` do próprio roteador,
com `router_rejected` como fallback estável quando o roteador não informar um código.

O grupo selecionado pelo roteador só é aceito se corresponder ao `routing_group` de um
modelo atualmente elegível: aprovado, com revisão vigente e com a classe de dado da
iniciativa entre suas classes permitidas. Isso fecha o follow-up do ADR 0019 e do
ADR 0020 — o roteador nunca pode aprovar um grupo que a governança não revisou
explicitamente, e a vigência calculada (`review_state`) é o critério usado, não o status
histórico.

## Alternatives considered

- **Confiar apenas na resposta do roteador:** rejeitado porque permitiria que um serviço
  externo expandisse o escopo aprovado sem revisão local, quebrando a garantia central
  desta plataforma.
- **Repetir a chamada `POST /route` em falha transitória:** rejeitado porque a operação
  não é idempotente; um retry poderia produzir uma segunda decisão divergente para a
  mesma tarefa sem meio confiável de deduplicar no lado do roteador.
- **Validar o escopo só antes da chamada externa, sem revalidar depois:** rejeitado
  porque uma revisão poderia expirar ou um ativo poderia ser alterado durante a chamada
  de rede, aprovando runtime sobre fatos já obsoletos.
- **Persistir apenas o resultado final, sem o registro `pending` inicial:** rejeitado
  porque uma falha do processo durante a chamada externa deixaria de gerar qualquer
  evidência da tentativa, contrariando a trilha de auditoria exigida pelo restante da
  plataforma.

## Consequences

- `routing_group` passa a ser um campo revisado de primeira classe: a revisão de
  Arquitetura de um modelo exige um grupo lógico explícito, e o marcador de migração
  `unassigned` é rejeitado tanto na revisão quanto na elegibilidade de runtime;
- toda revisão de modelo ou agente já existente é invalidada pela migração, porque seu
  digest anterior não vinculava `routing_group` (ver Operational impact);
- cada tentativa de roteamento custa duas idas ao banco e dois commits;
- credenciais do roteador são mapeadas por nome exato de agente revisado, nunca
  compartilhadas entre agentes;
- nenhum conteúdo de prompt ou documento é enviado ao roteador, apenas metadados
  operacionais e de risco já presentes no registro.

## Security and privacy impact

O payload enviado ao roteador contém somente workload, risco, classe de dado e limites
operacionais estimados — nunca prompt, documento ou identificador de usuário final. A
credencial por agente (`POLICY_MODEL_ROUTER_API_KEYS_JSON`) nunca aparece em `repr()` de
configuração nem em log. Indisponibilidade, resposta inválida ou credencial ausente
falham fechado como `dependency_unavailable`, nunca como aprovação implícita. A
auditoria registra apenas metadados e provenance (política, digest, grupo selecionado),
nunca o corpo de resposta bruto do roteador.

## Operational impact

A migração 0008 adiciona `routing_group` a `model_assets` com um valor de transição e,
em seguida, força todo modelo e agente já revisado de volta a `DRAFT` (exceto os já
`RETIRED`), porque nenhuma revisão anterior vinculava o novo campo ao digest aprovado.
Isso é um custo único de re-revisão esperado no deploy desta mudança, não um efeito
colateral a ser corrigido depois. `POLICY_MODEL_ROUTER_ENABLED` é opt-in (`false` por
padrão), então ambientes que não configurarem o roteador não são afetados. O roteador
externo em si não é operado por esta plataforma; sua disponibilidade e política de
decisão são responsabilidade do serviço `policy-model-router`.

## Follow-up

- Esta decisão fecha os follow-ups "integrar decisões ao `policy-model-router` para
  enforcement em runtime" (ADR 0019) e "usar `review_state=current` no adapter do
  `policy-model-router`" (ADR 0020).
- Cobrir com teste os caminhos 403/404 de autorização de `RequestModelRoutingDecision` e
  `ListModelRoutingDecisions`, e o próprio endpoint de listagem.
- Cobrir com teste unitário dedicado as guardas de imutabilidade e conflito de versão do
  `SqlAlchemyModelRoutingDecisionStore`, hoje só exercitadas indiretamente pelos testes
  de endpoint.
- Cobrir com teste o caso em que o escopo muda entre a aceitação do roteador e a
  releitura pós-chamada (`registry_scope_changed` depois de um `accepted`, e não apenas
  antes).
- Cobrir com teste modos adicionais de falha do adapter HTTP (JSON malformado, status
  inesperado como 500/401, cabeçalho `Content-Length` inválido).
- Exportar métricas agregadas de decisões por resultado (`allowed`/`blocked`/
  `dependency_unavailable`) e por `reason_code`, sem identificadores sensíveis.
