# Verifiable AI Governance

Plataforma de referência, independente de fornecedor, para cadastrar, avaliar, aprovar,
documentar e monitorar iniciativas e sistemas de IA. O MVP transforma requisitos de
governança em controles verificáveis, aprovações condicionais e evidências auditáveis.

## O que já está disponível

- portal Next.js voltado a solicitantes e aprovadores não técnicos;
- login do portal preparado para Microsoft Entra ID com MSAL, PKCE, cache de sessão e
  bearer token da API, mantendo modo local explicitamente separado;
- API FastAPI com autenticação OIDC validada contra provedor real;
- inventário navegável de iniciativas, sistemas, modelos e agentes, com ownership,
  versão, região, escopo de uso, autonomia, ferramentas e limites operacionais;
- estruturas persistentes preparadas para avaliações, evidências, incidentes e
  processamento internacional;
- classificação preliminar de risco e workflow condicional para Negócio, Arquitetura,
  Segurança, Infra, DevOps, Privacidade, Jurídico, Compliance e Dados;
- assessments estruturados e versionados para impacto de IA, RIPD e processamento
  internacional, com formulários guiados, risco residual e submissão para revisão;
- catálogo baseline com 25 controles em YAML, regras declarativas e visualização
  explicável de aplicabilidade por iniciativa;
- upload de evidências com allowlist, limite, validação de assinatura, SHA-256, scan
  ClamAV obrigatório, object storage privado e rollback compensatório;
- rodadas imutáveis de revisão, solicitação de ajustes, reabertura de assessments e
  ressubmissão com política e gates recalculados;
- segregação de funções, versionamento otimista e trilha de auditoria encadeada por hash;
- PostgreSQL local, migração inicial, testes e CI.

## Início rápido com Docker

Pré-requisito: Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
```

Antes de iniciar a API, o Compose executa `alembic upgrade head` em um serviço one-shot.
A API só recebe tráfego se a migração terminar com sucesso. O volume PostgreSQL é
preservado; não use `docker compose down -v` como procedimento de atualização.

Se a porta local do PostgreSQL já estiver ocupada, use por exemplo
`POSTGRES_PORT=55432 docker compose up --build`; a comunicação interna entre os
containers continua automática.

O Compose também inicia MinIO e ClamAV. Na primeira execução, o scanner pode levar
alguns minutos para preparar as assinaturas; até ficar disponível, uploads falham de
forma fechada com `503`. A imagem Debian oficial do ClamAV é fixada por digest
multi-arquitetura e funciona em hosts AMD64 e ARM64.

Abra o portal em <http://localhost:3000> e a documentação da API em
<http://localhost:8000/docs>.

O ambiente local exige identidade explícita, mesmo com OIDC desligado. O portal envia
um usuário de demonstração; chamadas manuais à API devem incluir `X-User-Id` e, para
aprovações, `X-User-Areas`.

## Desenvolvimento sem Docker para as aplicações

Pré-requisitos: Python 3.12+, `uv`, Node.js 20.9+ e PostgreSQL.

```bash
make setup
docker compose up -d postgres
make migrate
make dev-api
```

Em outro terminal:

```bash
make dev-web
```

## Qualidade

```bash
make test
make lint
make build
make quality
```

`make quality` executa o gate completo e reprodutível: lockfile, Ruff, mypy estrito,
testes Python, testes/lint do portal e build de produção. Configuração de deploy é
fornecida por variáveis de ambiente; `.env` é apenas uma conveniência local.

O catálogo padrão é empacotado com o `policy-engine`. Para fornecer uma política
organizacional diferente, configure `CONTROL_CATALOG_PATH` com o caminho de um YAML
válido. Arquivo ausente, schema inválido, IDs duplicados ou quantidade inesperada fazem
a aplicação falhar de forma fechada.

## Backup e restauração

O ambiente local possui um pacote portátil que combina dump lógico do PostgreSQL,
objetos privados de evidência e manifesto versionado com SHA-256. O fluxo nunca
sobrescreve um diretório, banco ou bucket existente. Para garantir consistência entre
os dois backing services, interrompa escritas da API durante a captura:

```bash
docker compose stop web api
make backup BACKUP_DIR=backups/2026-08-01
make backup-verify BACKUP_DIR=backups/2026-08-01
make backup-restore-test BACKUP_DIR=backups/2026-08-01
docker compose start api web
```

O restore test cria banco e bucket isolados, compara revisão Alembic, quantidade de
tabelas e checksums completos dos objetos, e então remove os destinos de teste. O
pacote contém dados potencialmente pessoais e confidenciais, recebe permissões locais
restritivas e deve ser criptografado, ter retenção definida e armazenamento externo
controlado. Consulte o [runbook de backup e restauração](docs/operations/BACKUP_RESTORE.md).

Uploads aceitam inicialmente PDF, PNG, JPEG, TXT, CSV e JSON até 10 MiB. O portal não
expõe bucket ou chave interna. Em ambientes não locais, desabilite
`OBJECT_STORAGE_AUTO_CREATE_BUCKET` e configure
`OBJECT_STORAGE_SERVER_SIDE_ENCRYPTION`; credenciais podem vir da cadeia padrão do
provedor em vez de variáveis estáticas.

## Fluxo do MVP

1. O solicitante cadastra uma proposta em linguagem de negócio.
2. O motor calcula risco preliminar e explica quais áreas precisam aprovar.
3. O owner preenche os assessments aplicáveis em rascunhos versionados e os envia para
   revisão independente; respostas completas não são copiadas para o audit log.
4. A submissão da iniciativa cria um gate para cada área; gates não aplicáveis ficam
   registrados.
5. Um aprovador autorizado, diferente do owner, registra decisão e justificativa.
6. Um revisor pode solicitar ajustes. A rodada e seus snapshots são preservados, os
   assessments voltam a rascunho e gates pendentes são encerrados.
7. O owner salva os fatos corrigidos para recalcular requisitos, conclui os assessments
   aplicáveis e então cria uma nova rodada sem reaproveitar aprovações anteriores.
8. Uma rejeição bloqueia a iniciativa. A aprovação só ocorre quando todos os gates
   obrigatórios da rodada atual forem aprovados.
9. O owner vincula sistemas de IA à iniciativa aprovada e registra seus modelos e
   agentes; ativos novos permanecem em rascunho até assurance posterior.
10. Alterações usam concorrência otimista, e aposentadorias preservam o histórico.
11. Toda mudança material gera evento de auditoria com versão e cadeia de hashes.
12. Evidências anexadas são validadas, vinculadas ao hash, escaneadas e armazenadas sem
    copiar conteúdo para logs ou PostgreSQL.

## Autenticação OIDC

Em ambientes compartilhados, defina `APP_ENV` diferente de `local`, habilite
`OIDC_ENABLED=true` e informe `OIDC_ISSUER`, `OIDC_JWKS_URL` e `OIDC_AUDIENCE`. A
aplicação se recusa a iniciar fora do ambiente local se OIDC estiver desabilitado ou
se issuer/JWKS não usarem HTTPS. O claim configurado em `OIDC_GROUPS_CLAIM` pode ser um
caminho aninhado, como `realm_access.roles`, e deve conter as áreas que o usuário pode
aprovar. Somente o booleano JSON `true` no `OIDC_ADMIN_CLAIM` concede administração.

Assinatura, issuer, audience, expiração, emissão e subject são obrigatoriamente
validados. Algoritmos simétricos não são aceitos. A obtenção de JWKS possui timeout e
cache configuráveis, e tokens excessivamente grandes são rejeitados antes do acesso ao
provedor.

### Validação local com Keycloak

O overlay opcional usa Keycloak exclusivamente como provedor de teste reproduzível. Ele
importa um realm local, emite um token RS256 com audience da API e mapeia o papel
`security` para `governance_areas`.

```bash
make oidc-up
make oidc-verify
make oidc-down
```

O validador confirma token real, mapeamento do grupo e rejeição de token ausente e de
assinatura adulterada. As senhas presentes no realm e em `.env.example` são somente
locais. O fluxo de senha direta existe apenas neste cliente de teste; autenticação
interativa do portal com authorization code e PKCE permanece no backlog.

A implementação corporativa usa Microsoft Entra ID para o login; o adapter do portal e
o enriquecimento Microsoft Graph via OBO estão implementados e aguardam validação em
tenant real.
No modo Entra, a API usa a identidade estável `(tid, oid)`, exige tenant allowlisted e
remove capacidades de aprovação de guests ou contas sem classificação `acct` confiável.
Quando habilitado, Microsoft Graph via OBO identifica automaticamente perfil e
departamento no endpoint `/api/v1/auth/me` e resolve grupos transitivos apenas
internamente. Quantidade e object IDs não são expostos e ainda não alteram autorização.
Áreas de aprovação virão
somente de App Roles ou object IDs explicitamente mapeados; departamento e nomes de
grupos não concedem autorização. Consulte também o
[runbook Graph OBO](docs/operations/MICROSOFT_GRAPH_OBO_SETUP.md).
Consulte o [plano Entra/Graph](docs/architecture/MICROSOFT_ENTRA_GRAPH_PLAN.md).

## Organização

```text
apps/web                     Portal Next.js
apps/api                     API FastAPI e persistência
packages/governance-schemas Contratos e taxonomias compartilhadas
packages/policy-engine       Classificação, controles e aplicabilidade
packages/document-templates Templates versionados de documentos
docs                         Produto, governança, arquitetura, ADRs e backlog
```

As integrações com `policy-model-router`, `a2a-otel-kit`,
`engineering-loop-schemas`, `alicerce` e `ragforge` estão definidas como portas futuras,
sem acoplar o núcleo do MVP a esses projetos.

## Aviso

Os templates e workflows apoiam governança, privacidade e compliance, mas não
constituem parecer jurídico nem alegação de conformidade ou certificação.
