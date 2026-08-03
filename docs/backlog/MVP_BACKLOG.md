# Backlog do MVP

## P0 — Tornar o núcleo utilizável

- [x] Monorepo, setup local, PostgreSQL, API, portal, testes e CI.
- [x] Cadastro, triagem, gates condicionais, SoD, auditoria e versionamento.
- [x] CRUD e telas de AI systems, modelos e agentes ligados à iniciativa aprovada.
- [x] Assessment estruturado para AIA, RIPD e processamento internacional.
- [x] Catálogo inicial de 25 controles em YAML e visualização de aplicabilidade.
- [x] Upload seguro de evidências com object storage, checksum do arquivo e malware scan.
- [x] Workflow de revisão, solicitação de ajuste e resubmissão sem apagar histórico.
- [x] Integração OIDC validada com ao menos um provedor e mapeamento de grupos.
- [x] Migrações explícitas e bloqueantes no startup do Compose.
- [x] Política de backup/restauração testada para PostgreSQL e evidências.
- [x] Tornar a imagem ClamAV do ambiente local compatível com hosts ARM64.

## P1 — Operação e assurance

- [x] Adapter do portal via Microsoft Entra ID, authorization code com PKCE e cache de sessão.
- [ ] Validação do login contra tenant Entra real e Conditional Access.
- [x] Identidade corporativa por `(tid, oid)`, tenant allowlist e política para guests.
- [x] Microsoft Graph via OBO para perfil, `department` e grupos transitivos do usuário.
- [x] Catálogo versionado de App Roles/object IDs Entra para áreas de aprovação.
- [ ] Group overage, paginação, throttling, cache, revogação e stale identity fail-closed.
  - [x] Paginação confiável, retry limitado, jitter e eventos de throttling sem conteúdo.
  - [x] Group overage explícito sem seguir URLs controladas pelo token.
  - [x] Cache PostgreSQL com TTL, freshness, binding ao catálogo e invalidação distribuída.
  - [x] Bloqueio/restauração emergencial persistente na plataforma, fail-closed e auditado.
  - [ ] Revogação de sessão no provedor e validação contra tenant Entra real.
- [x] Model/agent registry com approved scope, região, versão e datas de revisão.
- [x] Adapter de decisão do `policy-model-router`.
- [ ] Ingestão sanitizada de telemetria do `a2a-otel-kit`.
- [ ] Contratos de evidência inspirados em `engineering-loop-schemas`.
- [ ] Registro de execução isolada do `alicerce`.
- [ ] Importação de avaliações e regressões do `ragforge`.
- [x] Dashboard de violações, blocked actions, drift (indisponível), custo (limites) e revisões vencidas.
- [x] Incidentes, kill switch, exceções temporárias e plano de remediação.

## P2 — Escala e portfólio

- [ ] Overlays para serviços financeiros, RH, saúde e conhecimento corporativo.
- [ ] Crosswalk de apoio com NIST AI RMF, ISO/IEC 42001, NIST AI 600-1 e OWASP.
- [ ] Exportação de pacote de evidências para auditoria.
- [ ] APIs/webhooks para CMDB, catálogo de dados, CI/CD e GRC.
- [ ] Métricas executivas de cobertura, SLA, risco residual e efetividade de controles.

## Definition of done

Uma história não termina apenas com tela ou endpoint. Exige contrato, autorização,
persistência/versionamento quando aplicável, audit event, testes, documentação,
mensagens compreensíveis e comportamento seguro quando dependências falham.
