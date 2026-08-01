# ADR 0014 — Catálogo versionado de autorização Entra

## Status

Aceito.

## Date

2026-08-01.

## Context

A identidade corporativa já valida `(tid, oid)` e o adapter Microsoft Graph resolve
perfil e grupos transitivos. Até esta decisão, valores semelhantes a `ApprovalArea`
poderiam vir diretamente do claim configurado. Isso não oferece uma política explícita
tenant-specific, uma versão da decisão nem um identificador auditável do mapeamento.

`department`, e-mail e nomes de grupos são mutáveis e inadequados para autorização.
Mesmo App Roles e object IDs confiáveis precisam de ownership, revisão e associação
explícita à taxonomia interna.

## Decision

A autorização corporativa passa a usar um catálogo YAML imutável, validado no startup e
versionado como código. O catálogo possui ID e versão globais; cada mapping possui ID,
tenant UUID, tipo de fonte, valor, `ApprovalArea`, estado, owner e versão própria.

As fontes aceitas são:

- `app_role`, comparada de forma exata e case-sensitive com o claim Entra configurado
  por `OIDC_ENTRA_APP_ROLES_CLAIM`;
- `group`, comparada somente com object IDs UUID obtidos das associações transitivas do
  Microsoft Graph.

Em modo Entra, claims deixam de conceder `ApprovalArea` diretamente. Eles fornecem
somente App Role values para o resolver. O catálogo empacotado é vazio e, portanto, não
concede capacidade por padrão. Um deployment pode usar um arquivo externo por
`DIRECTORY_AUTHORIZATION_CATALOG_PATH`; falha no override não possui fallback.

Somente `/api/v1/auth/me`, decisões de aprovação e consulta ao histórico de revisão
usam o principal completamente autorizado. Rotas que precisam apenas de autenticação
não chamam o Graph. Mapeamentos de App Role podem funcionar sem Graph; mapeamentos de
grupo falham fechados quando o perfil transitivo não está disponível.

Member pode receber mappings. Guest somente quando a política explícita existente
habilitar aprovações; conta de tipo desconhecido nunca recebe. Administração continua
como capacidade separada, restrita a member e ao claim booleano já validado.

A provenance exposta ao próprio usuário contém somente catálogo, versão, digest
semântico SHA-256, mapping IDs e tipos de fonte. O evento de decisão de aprovação
registra a mesma evidência na cadeia de auditoria, sem App Roles brutas ou inventário
de grupos.

## Alternatives considered

- Mapear valores do claim diretamente para `ApprovalArea`: rejeitado por não possuir
  tenant, owner, versão ou decisão explícita.
- Usar `department` ou display names: rejeitado por mutabilidade e colisão.
- Persistir o catálogo em tabelas e criar CRUD administrativo: adiado. A política como
  código oferece revisão, histórico e rollback suficientes para esta etapa com menor
  superfície de ataque.
- Conceder áreas do catálogo padrão: rejeitado porque nenhum tenant ou object ID real
  deve existir como default do produto.
- Consultar Graph em toda request: rejeitado para limitar latência, dados e impacto de
  indisponibilidade às rotas que realmente dependem de capacidade de revisão.
- Registrar todos os grupos e roles na auditoria: rejeitado por minimização e risco de
  criar um inventário paralelo de acesso.

## Consequences

Deployments Entra precisam publicar um catálogo tenant-specific antes de seus usuários
receberem áreas de aprovação. OIDC genérico e autenticação local preservam o mapeamento
existente para testes e integrações não Entra.

Mudanças são revisáveis em Git, deterministicamente testáveis e vinculadas à decisão
por versão e mapping IDs. Não existe migração de banco nesta entrega. Uma mudança de
arquivo exige reinício do processo para carregar a nova política.

O catálogo atual representa somente o estado ativo; histórico e aprovação formal vêm
do repositório e de suas regras de branch protection.

## Security and privacy impact

O padrão vazio, o matching tenant-specific, a validação estrita, UUIDs canônicos,
limites de tamanho/quantidade, IDs opacos e o bloqueio de duplicidades reduzem
concessões acidentais. Campo desconhecido, booleano ou inteiro textual, source type
inválido e `ApprovalArea` desconhecida impedem o startup. O digest diferencia conteúdo
alterado mesmo quando alguém esquece de incrementar a versão declarada.

App Role values e object IDs são dados de controle de acesso. Eles permanecem no token,
Graph e arquivo protegido, mas não são retornados nem copiados para eventos. Mapping IDs
devem ser identificadores não sensíveis. `department` permanece fora da autorização.

Graph ou catálogo indisponível não promove o principal. Guest e identidade ambígua
continuam sem capacidades por padrão. Segregação de funções permanece aplicada pelo
domínio de revisão após a resolução da área.

## Operational impact

IAM, Segurança e Governança de IA precisam definir reviewers e branch protection para
o arquivo organizacional. O deployment deve montar o catálogo como read-only, apontar a
variável de ambiente e reiniciar de forma controlada. Publicação deve testar caso
permitido, negado, outro tenant, guest e grupo removido.

Revogação imediata exige nova versão, publicação e reinício enquanto cache não existe.
Rollback republica uma revisão Git anteriormente aprovada. Métricas devem distinguir
falha do catálogo, indisponibilidade Graph e ausência legítima de mapping.

## Follow-up

- Implementar cache curto, invalidação, revogação urgente e stale identity fail-closed.
- Tratar group overage e claims de grupos sem seguir URLs controladas por token.
- Adicionar retry limitado, jitter e monitoramento do Graph.
- Avaliar workflow administrativo persistido quando escala e segregação exigirem UI.
- Avaliar migração da administração global para política versionada própria.
