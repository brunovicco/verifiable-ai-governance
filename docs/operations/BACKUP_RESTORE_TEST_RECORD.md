# Registro de teste de backup e restauração

## Execução 2026-08-01

| Campo | Resultado |
|---|---|
| Ambiente | Compose local em host ARM64 |
| PostgreSQL | 17.10 |
| MinIO | RELEASE.2025-04-22T22-12-26Z |
| Revisão capturada | `0004` |
| Tabelas públicas | 12 |
| Metadados de uploads S3 | 0 |
| Objetos S3 de origem | 0; bucket ainda não materializado |
| Permissão do diretório | `0700` |
| Permissão dos arquivos | `0600` |
| Create | aprovado |
| Verify de hashes e catálogo | aprovado |
| Restore isolado | aprovado |
| Limpeza do banco temporário | aprovada; 0 bancos `governance_restore_%` restantes |
| Preservação da origem | revisão `0004`, 1 iniciativa, 9 gates e 1 evidência preservados |

O teste real utilizou um dump de 33.245 bytes e restaurou a revisão e as 12 tabelas em
um banco novo. Também criou e removeu um bucket S3 isolado. A origem não possuía uploads
armazenados no S3; exportação, upload, releitura por SHA-256 e remoção de conteúdo não
vazio são cobertos pelo teste determinístico do adapter.

Esse registro comprova a execução do fluxo no ambiente de referência, mas não define
RPO, RTO ou conformidade de produção. A primeira implantação corporativa deve executar
novo restore test com evidências representativas não produtivas, criptografia e
serviços gerenciados escolhidos pela organização.
