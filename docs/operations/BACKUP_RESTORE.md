# Runbook de backup e restauração

## Objetivo e escopo

Este runbook protege os dois backing services que formam o registro verificável:

- PostgreSQL, que contém iniciativas, decisões, assessments, metadados e auditoria;
- object storage S3, que contém os arquivos privados de evidência referenciados pelo
  banco.

O utilitário do repositório é uma referência executável para ambiente local ou
controlado. Produção deve usar as capacidades gerenciadas equivalentes, como PITR,
snapshots criptografados, versionamento de objetos e replicação, preservando o mesmo
manifesto, assurance e critérios de acesso.

## Garantias do pacote

Cada pacote é criado em diretório temporário privado e publicado por rename atômico
somente depois da conclusão. Ele contém:

```text
backup/
├── manifest.json
├── manifest.sha256
├── postgres.dump
└── evidence/
    └── arquivos identificados por índice e hash da chave
```

O manifesto registra versão do formato, timestamp com fuso, origem lógica, revisão
Alembic, quantidade de tabelas e, para cada artefato, caminho, tamanho e SHA-256. As
chaves de objetos ficam no manifesto, mas não aparecem no output operacional. Hashes
detectam corrupção; não substituem assinatura, controle de acesso ou armazenamento
imutável contra um atacante capaz de substituir pacote e manifesto.

A quantidade de objetos do bucket é comparada aos metadados de uploads confiáveis no
banco. Um bucket ainda não criado só representa inventário vazio quando o banco também
não referencia objetos; divergências interrompem a captura de forma fechada.

Diretórios existentes, bancos existentes e buckets existentes nunca são
sobrescritos. O restore aceita apenas nomes de banco simples e um bucket S3 válido,
sempre distintos das origens configuradas.

## Pré-requisitos

- serviços `postgres` e `object-storage` do Compose saudáveis;
- `uv` e dependências sincronizadas;
- espaço livre suficiente para o dump e todos os objetos;
- acesso exclusivo e destino criptografado para o pacote;
- janela de manutenção ou outro mecanismo que impeça novos uploads e alterações.

O utilitário lê configuração do ambiente conforme Twelve-Factor. Os defaults atendem
ao Compose local. Em outra configuração, forneça `POSTGRES_DB`, `POSTGRES_USER`,
`BACKUP_OBJECT_STORAGE_ENDPOINT_URL`, `OBJECT_STORAGE_REGION`,
`OBJECT_STORAGE_BUCKET` e credenciais de curta duração por mecanismo seguro. As
variáveis `BACKUP_OBJECT_STORAGE_ACCESS_KEY`, `BACKUP_OBJECT_STORAGE_SECRET_KEY` e
`BACKUP_OBJECT_STORAGE_SESSION_TOKEN` têm precedência e permitem uma identidade de
least privilege separada da aplicação; quando ausentes, o adapter aceita a cadeia
padrão do SDK.
Timeouts e retries também são configuração explícita por
`BACKUP_DATABASE_COMMAND_TIMEOUT_SECONDS`, `BACKUP_S3_CONNECT_TIMEOUT_SECONDS`,
`BACKUP_S3_READ_TIMEOUT_SECONDS` e `BACKUP_S3_MAX_ATTEMPTS`.

## Criar e verificar

Escolha um diretório novo; o comando falha se ele já existir.

```bash
docker compose stop web api
make backup BACKUP_DIR=backups/2026-08-01
make backup-verify BACKUP_DIR=backups/2026-08-01
make backup-restore-test BACKUP_DIR=backups/2026-08-01
docker compose start api web
```

`backup-verify` recalcula todos os hashes e pede ao `pg_restore` para ler o catálogo.
`backup-restore-test` cria destinos aleatórios, restaura todo o conteúdo, compara o
estado do banco, relê os objetos para validar SHA-256 e remove os destinos isolados.
Um teste que não conclui a limpeza retorna falha e exige intervenção operacional.

Após sucesso:

1. registrar identificador, horário, ambiente, revisão Alembic, contagens e resultado;
2. criptografar o pacote com chave administrada fora do próprio backup;
3. mover uma cópia para local com domínio de falha e acesso independentes;
4. aplicar retenção e descarte aprovados por Privacidade, Segurança e Records
   Management;
5. monitorar idade do último backup válido e do último restore testado.

## Restauração controlada

O comando restaura apenas para destinos inexistentes. Isso permite validar e promover
por cutover, sem destruir a origem:

```bash
make backup-restore \
  BACKUP_DIR=backups/2026-08-01 \
  RESTORE_DATABASE=ai_governance_recovered \
  RESTORE_BUCKET=governance-evidence-recovered
```

Antes do cutover:

1. confirmar o resultado JSON e executar smoke tests com configuração isolada;
2. conferir revisão Alembic, contagens, amostra autorizada de evidências e cadeia de
   auditoria;
3. registrar aprovação de Operações, owner do sistema e Segurança/Privacidade quando
   aplicável;
4. trocar endpoints por configuração de deploy, sem renomear ou apagar a origem;
5. manter rollback até o aceite e só então aplicar a política de descarte.

O restore não executa migrations adicionais. O pacote deve ser restaurado no estado
em que foi capturado; qualquer upgrade ocorre depois, pelo processo explícito e
bloqueante já adotado pelo projeto.

## Política organizacional mínima

RPO, RTO, frequência e retenção devem ser aprovados por risco e obrigação legal; o
framework não inventa um valor universal. A política da organização precisa definir:

- objetivos mensuráveis por tier e owner responsável;
- backups automáticos, alertas e teste periódico de restauração;
- criptografia em trânsito e repouso, segregação de funções e least privilege;
- imutabilidade ou proteção contra exclusão maliciosa e ransomware;
- localização de backups, subprocessadores e avaliação de transferência
  internacional;
- retenção coerente entre banco, evidências, auditoria e solicitações de titulares;
- procedimento de incidente, comunicação e coleta de evidência operacional.

Nunca inclua credenciais, chaves de criptografia ou logs com conteúdo de evidência no
mesmo pacote. Não publique backups em Git, artifacts de CI públicos ou buckets sem
política privada explícita.

## Falhas e recuperação operacional

- Falha no create: o diretório temporário não é publicado e é removido.
- Hash divergente ou catálogo ilegível: coloque o pacote em quarentena e use outra
  cópia; não force o restore.
- Destino já existente: escolha um destino novo e investigue a origem do conflito.
- Restore parcial: o caso de uso remove destinos criados por aquela tentativa.
- Cleanup do restore test falhou: trate como incidente operacional e remova somente os
  destinos exatos informados no resultado/erro após confirmação independente.
- Fonte indisponível: preserve logs técnicos minimizados e acione o owner do backing
  service; não degrade para backup parcial.
