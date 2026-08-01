# Catálogo de autorização do diretório corporativo

## Objetivo

O catálogo converte valores estáveis do Microsoft Entra ID em áreas de aprovação da
plataforma. Ele é uma política versionada e fail-closed: App Role, grupo, nome,
`department` ou outra informação não mapeada não concede capacidade.

O catálogo padrão empacotado não contém mapeamentos. Uma organização deve criar seu
arquivo tenant-specific, revisá-lo e disponibilizá-lo ao deployment por caminho
explícito.

## Estrutura

Use `docs/examples/entra-authorization-catalog.yaml` como referência:

```yaml
catalog_id: enterprise-entra-authorization
catalog_version: "2026.08.1"
mappings:
  - mapping_id: entra-role-security-reviewer
    tenant_id: 11111111-1111-4111-8111-111111111111
    source_type: app_role
    source_value: Governance.Security.Reviewer
    approval_area: security
    enabled: true
    owner: identity-and-access-management
    mapping_version: 1
```

Campos:

- `catalog_id`: identidade estável da política;
- `catalog_version`: versão integral alterada a cada publicação;
- `mapping_id`: identidade estável do mapeamento, usada em auditoria;
- `tenant_id`: UUID do tenant ao qual o mapeamento pertence;
- `source_type`: `app_role` ou `group`;
- `source_value`: valor exato da App Role ou object ID UUID do grupo;
- `approval_area`: valor da taxonomia corporativa `ApprovalArea`;
- `enabled`: booleano YAML real, nunca texto;
- `owner`: área responsável pela origem e revisão;
- `mapping_version`: inteiro positivo incrementado quando o registro muda.

App Roles são case-sensitive. Grupos são comparados somente por object ID canônico.
`displayName`, e-mail, UPN, cargo e `department` nunca participam da decisão.

## Configuração

O access token da API deve conter o claim de App Roles configurado. Para Entra, o
default é `roles`:

```dotenv
OIDC_ENTRA_APP_ROLES_CLAIM=roles
DIRECTORY_AUTHORIZATION_CATALOG_PATH=/run/governance/entra-authorization.yaml
```

Monte o arquivo como read-only no container. Caminho ausente, YAML inválido, campo
desconhecido, tipo ambíguo, UUID inválido ou mapeamento duplicado impedem o startup. A
aplicação não retorna ao catálogo empacotado quando o override falha.

Mapeamentos `app_role` funcionam somente a partir do claim verificado. Mapeamentos
`group` exigem Microsoft Graph habilitado para resolver associações transitivas. Se o
Graph estiver desabilitado, um claim `groups` completo e validado também pode fornecer
os object IDs. Overage, claim ausente ou inválido nunca concede capacidade de grupo; se
um snapshot Graph confiável existir, ele prevalece sobre o token.

## Workflow de mudança

1. IAM confirma o tenant, App Role ou object ID, owner e necessidade de acesso.
2. Governança de IA confirma a correspondência com `ApprovalArea` e o escopo da área.
3. Segurança revisa menor privilégio, segregação de funções e impacto de guest.
4. O autor altera o mapping e incrementa `mapping_version` e `catalog_version`.
5. CI executa validação de YAML, testes de domínio e quality gate completo.
6. Revisores independentes aprovam o pull request conforme branch protection.
7. O deployment recebe o arquivo aprovado como configuração read-only e reinicia.
8. A validação confirma `/api/v1/auth/me`, decisão permitida e decisão negada.

O repositório demonstra o workflow, mas a organização precisa configurar os reviewers
reais de IAM, Segurança e Governança de IA no GitHub.

## Auditoria e minimização

`/api/v1/auth/me` retorna:

- áreas efetivas;
- ID e versão do catálogo;
- digest SHA-256 semântico do catálogo;
- IDs dos mappings aplicados;
- tipos de fonte aplicados.

O endpoint não retorna App Roles brutas, grupos, quantidade de grupos ou nomes. Uma
decisão de aprovação registra a mesma provenance no evento hash-chained. Isso vincula
a decisão à política sem persistir o inventário integral de associações do usuário.

## Revogação e rollback

Para revogar capacidade:

1. desabilite ou remova o mapping;
2. incremente as versões;
3. conclua revisão emergencial conforme o processo de acesso;
4. publique e reinicie o deployment;
5. o novo digest torna os snapshots anteriores inelegíveis;
6. valide que a área desapareceu e a decisão é negada.

Rollback significa republicar uma versão anteriormente aprovada do arquivo, nunca
editar a trilha Git.

Para forçar revalidação imediata de uma única identidade, um administrador chama
`POST /api/v1/auth/directory-authorization-cache/invalidate` com `tenant_id`,
`object_id`, um motivo enumerado e uma referência opcional de ticket. A operação limpa
o snapshot no PostgreSQL e grava evento auditável na mesma transação, sem copiar os IDs
do alvo para o payload do evento. O tenant deve constar em
`OIDC_ALLOWED_TENANT_IDS`. A próxima operação sensível precisa obter um novo resultado
confiável. Isso não remove App Role, grupo, sessão ou conta no Entra; a revogação
definitiva continua sob responsabilidade de IAM.

Se a identidade inteira precisar ser contida, use
`POST /api/v1/auth/directory-access/block`. Esse comando impede a próxima request
protegida em todas as réplicas, invalida o cache e grava auditoria na mesma transação.
Restauração usa `/directory-access/restore` e exige nova resolução de autorização. O
procedimento completo está em `DIRECTORY_ACCESS_INCIDENT_RESPONSE.md`.

## Validação mínima

- App Role exata concede somente a área mapeada;
- App Role com capitalização diferente não concede;
- grupo transitivo mapeado concede somente com Graph confiável;
- grupo com mesmo nome e outro object ID não concede;
- mapping de outro tenant, desabilitado ou duplicado não concede;
- guest não concede por padrão;
- conta com tipo desconhecido não concede;
- falha de catálogo ou Graph bloqueia a operação sensível;
- auditoria contém mapping IDs, versão e digest, sem valores brutos da origem.
