# ADR 0010 — Backup portátil e restauração isolada

## Status

Aceito.

## Date

2026-08-01.

## Context

O PostgreSQL guarda decisões, snapshots, metadados de evidência e a trilha de
auditoria. Os bytes das evidências ficam em object storage privado. Proteger apenas um
desses serviços produz uma restauração incompleta: registros podem apontar para
objetos ausentes, ou objetos podem perder seu contexto, owner e retenção.

O Compose já preserva volumes e bloqueia o startup da API até a migração explícita,
mas volume persistente não é backup. O incidente de schema defasado documentado no ADR
0009 também evidenciou a necessidade de provar recuperação sem alterar o banco
principal.

## Decision

Adotaremos um pacote lógico e portátil para o ambiente de referência, composto por:

- dump PostgreSQL custom-format gerado por `pg_dump`, sem ownership ou privilégios;
- cópia de todos os objetos do bucket privado por API S3;
- manifesto imutável e versionado com provenance, revisão Alembic, contagens, tamanhos
  e SHA-256;
- checksum separado do manifesto para detectar corrupção acidental;
- criação em diretório privado temporário e publicação atômica;
- verificação por recálculo de hashes e leitura do catálogo pelo `pg_restore`;
- restauração apenas em banco e bucket inexistentes;
- restore test em destinos aleatórios isolados, com comparação do estado e limpeza.

O fluxo depende de portas pertencentes à camada de aplicação. Adapters implementam
filesystem local, ferramentas PostgreSQL via Compose e S3 compatível. A CLI apenas
compõe essas dependências e lê configuração do ambiente.

Como PostgreSQL e S3 não compartilham transação, a captura exige janela sem escrita ou
mecanismo equivalente de quiesce. Em produção, serviços gerenciados podem substituir
os adapters, desde que preservem consistência, integridade e restore assurance.

## Alternatives considered

- Copiar somente o volume Docker: rejeitado por não ser portátil, depender do layout
  da imagem e não demonstrar recuperação lógica.
- Fazer backup apenas do PostgreSQL: rejeitado porque excluiria os bytes das evidências.
- Fazer backup apenas do bucket: rejeitado porque perderia contexto, autorização e
  audit trail.
- Restaurar sobre o banco e bucket originais: rejeitado pelo risco de destruição e pela
  impossibilidade de validar antes do cutover.
- Considerar o checksum suficiente contra adulteração: rejeitado; ele detecta
  corrupção, mas autenticidade exige controle externo, imutabilidade ou assinatura.

## Consequences

O projeto passa a ter um caminho reproduzível para captura, verificação e recuperação
dos dois backing services. O manifesto permite explicar e auditar o conteúdo sem
expor dados no output do comando.

O pacote pode ser grande, o restore test duplica temporariamente armazenamento e a
captura consistente exige coordenação operacional. O formato terá de evoluir de forma
compatível quando novos backing services forem adicionados.

## Security and privacy impact

O pacote contém dados pessoais, informações confidenciais e evidências. Arquivos e
diretórios locais recebem permissões restritivas, chaves de objeto e conteúdos não são
logados, e credenciais vêm do ambiente. Paths, nomes de destinos, tamanhos e hashes são
validados antes de uso.

SHA-256 não cifra nem autentica contra substituição coordenada. Backups reais devem
usar criptografia, gestão separada de chaves, least privilege, retenção, descarte,
imutabilidade e armazenamento fora do domínio de falha. Localização, suporte e cópias
internacionais entram no assessment de processamento internacional.

## Operational impact

Operações deve monitorar idade do último backup válido e do último restore testado,
capacidade, duração, falhas e limpeza de destinos temporários. RPO e RTO continuam
decisões organizacionais por risco.

O restore não aplica migrations além do estado capturado. A promoção ocorre por
configuração e cutover após smoke test e aprovação, preservando a origem para rollback.

## Follow-up

- Integrar o procedimento a um scheduler e alertas de produção.
- Definir RPO, RTO, retenção e frequência por tier de risco.
- Adicionar assinatura ou attestation do manifesto em ambiente corporativo.
- Testar adapters de backup gerenciado e object storage com versionamento.
- Registrar resultados periódicos como evidência de controle operacional.

