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
- [ ] Política de backup/restauração testada.
- [x] Tornar a imagem ClamAV do ambiente local compatível com hosts ARM64.

## P1 — Operação e assurance

- [ ] Login do portal via Microsoft Entra ID, authorization code com PKCE e sessão segura.
- [ ] Identidade corporativa por `(tid, oid)`, tenant allowlist e política para guests.
- [ ] Microsoft Graph via OBO para perfil, `department` e grupos transitivos do usuário.
- [ ] Catálogo versionado de App Roles/object IDs Entra para áreas de aprovação.
- [ ] Group overage, paginação, throttling, cache, revogação e stale identity fail-closed.
- [ ] Model/agent registry com approved scope, região, versão e datas de revisão.
- [ ] Adapter de decisão do `policy-model-router`.
- [ ] Ingestão sanitizada de telemetria do `a2a-otel-kit`.
- [ ] Contratos de evidência inspirados em `engineering-loop-schemas`.
- [ ] Registro de execução isolada do `alicerce`.
- [ ] Importação de avaliações e regressões do `ragforge`.
- [ ] Dashboard de violações, blocked actions, drift, custo e revisões vencidas.
- [ ] Incidentes, kill switch, exceções temporárias e plano de remediação.

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
