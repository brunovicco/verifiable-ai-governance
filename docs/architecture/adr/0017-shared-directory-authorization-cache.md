# ADR 0017 - Cache compartilhado de autorização de diretório

## Status

Aceito.

## Date

2026-08-01.

## Context

As rotas sensíveis resolviam o Microsoft Graph em cada request quando a integração OBO
estava habilitada. Isso ampliava latência e exposição a throttling. Um cache apenas em
memória reduziria chamadas, mas permitiria decisões diferentes entre réplicas e não
ofereceria uma invalidação administrativa única.

Autorização não pode reutilizar indefinidamente uma associação removida. Também não
deve transformar o cache em um diretório paralelo contendo token, perfil ou inventário
de grupos do usuário.

## Decision

O PostgreSQL será o store compartilhado de snapshots de autorização derivados. A chave
é a identidade estável `(tenant_id, object_id)` e o ID persistido é um UUID determinístico.
Cada snapshot contém somente:

- áreas de aprovação efetivas;
- ID, versão e digest do catálogo;
- IDs de mappings aplicados e tipos abstratos de fonte;
- fonte original da resolução;
- `resolved_at`, `expires_at`, `invalidated_at` e versão.

Bearer token, access token OBO, nome, e-mail/UPN, departamento, resposta Graph e object
IDs de grupos não são persistidos.

O TTL vem de `DIRECTORY_AUTHORIZATION_CACHE_TTL_SECONDS`, com default de 60 segundos e
limite de 5 a 300 segundos. O núcleo reutiliza um snapshot somente quando:

1. a identidade autenticada coincide exatamente com a chave;
2. `now < expires_at`;
3. o digest coincide com o catálogo carregado;
4. não existe invalidação igual ou posterior à resolução.

Miss, expiração, mudança do catálogo ou invalidação exigem resolução ao vivo. Se o
Graph necessário estiver indisponível, a operação falha fechada. Overage não resolvido
nunca é armazenado.

Writes usam upsert nativo. O horário da resolução é capturado antes da chamada remota:
um refresh iniciado antes de uma invalidação não a substitui, mesmo que o Graph responda
depois. Uma resolução realmente posterior pode publicar novo snapshot; resolução
anterior ou simultânea é rejeitada.

O endpoint administrativo
`POST /api/v1/auth/directory-authorization-cache/invalidate` aceita a identidade-alvo,
um motivo enumerado e referência opcional de ticket. Ele remove o conteúdo derivado,
mantém um marcador de invalidação compartilhado e inclui evento hash-chained na mesma
transação. O payload de auditoria usa digest do alvo, motivo e referência, não os UUIDs
brutos. O tenant-alvo precisa pertencer à allowlist confiável do deployment.

## Alternatives considered

- Cache local em memória: rejeitado por divergência entre réplicas e invalidação não
  distribuída.
- Redis no MVP: adiado para evitar nova dependência operacional; PostgreSQL já fornece
  consistência e transação conjunta com auditoria no volume atual.
- Persistir perfil e grupos: rejeitado por minimização, retenção e risco de criar um
  diretório secundário.
- Usar snapshot expirado durante falha do Graph: rejeitado porque disponibilidade não
  pode ampliar o período de acesso.
- Tratar invalidação como revogação definitiva: rejeitado. Cache controla freshness;
  IAM e Entra continuam sendo a autoridade sobre conta, sessão, grupos e App Roles.

## Consequences

Chamadas de autorização dentro do TTL podem evitar OBO e Graph, enquanto `/auth/me`
ainda pode buscar o perfil mínimo para exibição. Todas as réplicas observam o mesmo
snapshot e marcador de invalidação.

A migração `0005` cria uma tabela descartável. Downgrade remove somente cache e
marcadores; a cadeia de auditoria permanece. Deployments precisam executar a migração
antes de subir a API.

PostgreSQL passa a integrar o caminho de autorização corporativa. Falha de leitura ou
commit retorna erro seguro em vez de continuar sem o controle compartilhado.
Leituras usam uma sessão curta e liberam a conexão antes de qualquer chamada ao Graph;
o adapter não mantém transação de banco aberta enquanto espera uma dependência remota.

## Security and privacy impact

O cache possui autorização derivada e deve receber os mesmos controles de acesso,
backup e criptografia do banco. Mesmo sem grupos brutos, áreas e mappings são dados de
controle de acesso. A retenção operacional pode remover linhas expiradas no futuro,
sem apagar eventos de auditoria.

A invalidação exige `is_admin`, que no modo Entra depende do claim booleano confiável e
é removido de guest ou conta ambígua. Referências são identificadores curtos de ticket,
não texto livre.

## Verification

- testes de domínio cobrem identidade, digest, expiração e invalidação;
- testes de aplicação cobrem overage não armazenado e corrida com invalidação;
- testes do adapter cobrem round-trip, marcador compartilhado e refresh posterior;
- teste HTTP cobre negação para não administrador e auditoria sem UUIDs do alvo;
- a migração deve passar por upgrade, downgrade para `0004` e novo upgrade em
  PostgreSQL real.

## Follow-up

- integrar a restrição local definida no ADR 0018 à futura revogação de sessão no Entra;
- validar remoção real de grupo, guest, Conditional Access e SLA em tenant não
  produtivo;
- exportar métricas agregadas de hit, miss, expiração, invalidação e falha, sem
  identificadores de usuários;
- definir limpeza periódica de entradas expiradas e política de retenção.
