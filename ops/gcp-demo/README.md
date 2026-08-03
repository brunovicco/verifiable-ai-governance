# IaC — Verifiable AI Governance no Google Cloud (Compute Engine)

Terraform que provisiona **tudo**: VPC, subnet, firewall, IP externo
(estatico, opcional), a instancia Compute Engine, e — via `cloud-init.sh.tpl`
como `user-data` — a configuracao completa do SO (swap, Docker), o clone do
repositorio, o `docker compose up`, a semeadura de dados de exemplo
(`scripts/seed_demo_data.py`, dez iniciativas `[DEMO]` cobrindo o fluxo
inteiro) e o Caddy com TLS automatico.

A demo fica **publica e sem credencial**, mas **somente leitura**: qualquer
visitante acessa o portal e "loga" com uma identidade local autodeclarada
(modo dev do app, sem verificacao real — ver `NEXT_PUBLIC_AUTH_MODE=local`),
consegue navegar e ler os dados, mas o Caddy bloqueia no dominio da API
qualquer metodo que nao seja `GET`/`HEAD`/`OPTIONS` com `403` antes de chegar
no backend — ninguem consegue criar, editar ou apagar nada pela demo publica.
Isso e intencional (demo aberta pra visitacao, sem autenticacao real ainda),
nao uma protecao de producao — trate como tal ate o Entra ID entrar (ver
["Migrar para Entra ID depois"](#migrar-para-entra-id-depois)).

Equivalente ao modulo [`ops/oci-demo/`](../oci-demo/), trocando a nuvem: o
`cloud-init.sh.tpl` e identico nos dois (nao ha nada especifico de OCI ou GCP
nele - Docker/Caddy/git clone sao genericos). Use este modulo se a
capacidade Ampere A1 Always Free da OCI estiver indisponivel na sua regiao,
ou se preferir GCP por qualquer outro motivo.

Diferente da OCI, o GCP **nao tem tier Always Free com RAM suficiente** para
esta stack (o free-forever de verdade e uma `e2-micro` com ~1GB, insuficiente
para Postgres + MinIO + ClamAV + build do Next.js simultaneos). Este modulo
usa `e2-standard-2` (2 vCPU/8GB) por padrao, pensado para caber com folga no
credito de US$ 300/90 dias que contas novas do GCP recebem - depois disso a
instancia passa a ser cobrada normalmente enquanto ficar no ar.

## Pre-requisitos

1. **Conta GCP** com um projeto criado e billing habilitado (o credito de
   US$ 300/90 dias exige cartao para validacao, mas nao cobra nada dentro do
   credito). Anote o **Project ID** (nao o nome de exibicao) em Console →
   seletor de projeto no topo.
2. **gcloud CLI** instalado localmente:
   ```bash
   brew install google-cloud-sdk   # macOS; veja https://cloud.google.com/sdk/docs/install para outros SOs
   ```
3. **Autenticacao** — duas etapas, a segunda e a que o Terraform de fato usa:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   gcloud config set project <SEU_PROJECT_ID>
   ```
4. **Habilitar a API do Compute Engine** no projeto (senao o `apply` falha
   no primeiro recurso):
   ```bash
   gcloud services enable compute.googleapis.com
   ```
5. **Terraform** >= 1.6 instalado localmente.
6. Um par de chaves SSH dedicado:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/gcp-vai-demo -C "vai-demo"
   ```
7. Dois dominios/subdominios (`app.` e `api.`) que voce controla — pode
   reaproveitar os mesmos do modulo OCI (ex: DuckDNS), so precisam apontar
   para o IP novo depois do apply.

## Uso

```bash
cp terraform.tfvars.example terraform.tfvars
# edite terraform.tfvars com seu project_id, CIDR do seu IP, dominios, etc.

terraform init
terraform plan
terraform apply
```

Ao final, o Terraform imprime o IP publico (`instance_public_ip`). Aponte os
registros DNS tipo A de `app_domain` e `api_domain` para esse IP. O Caddy ja
esta rodando e emite o certificado Let's Encrypt automaticamente assim que o
DNS propagar e a primeira requisicao chegar.

Recupere as credenciais geradas quando precisar:
```bash
terraform output postgres_password
terraform output minio_password
terraform output audit_hash_salt
```

## Migrar para Entra ID depois

Mesmo procedimento do modulo OCI: entre via SSH na instancia, edite
`/opt/vai-governance/.env` com os valores de `OIDC_ISSUER`, `OIDC_JWKS_URL`,
`OIDC_AUDIENCE`, os App Registrations do Entra e os `NEXT_PUBLIC_ENTRA_*`,
rode `docker compose up --build -d` para aplicar o rebuild do `web`, e
remova o bloco `@write`/`respond` de `/etc/caddy/Caddyfile` no site do
`$API_DOMAIN` (seguido de `systemctl reload caddy`) ja que a autorizacao
passa a ser feita de verdade pelo Entra ID em vez do bloqueio de metodo na
borda.

## Observacoes importantes

- **Custo**: ao contrario do modulo OCI, esta infraestrutura **nao e
  gratuita para sempre** — depende do credito promocional de conta nova ou
  de cobranca normal do Compute Engine depois. Rode `terraform destroy`
  quando terminar de usar a demo se quiser evitar cobranca continua.
- **Segredos no state**: `postgres_password`, `minio_password` e
  `audit_hash_salt` ficam no `terraform.tfstate` em texto plano
  (comportamento padrao do provider `random`). Nao versione o state em um
  repositorio publico.
- **Idempotencia do cloud-init**: o script roda uma unica vez no primeiro
  boot. Para reaplicar mudancas de app, entre via SSH e rode
  `git pull && docker compose up --build -d` manualmente, ou destrua e
  reaplique a instancia (`terraform taint google_compute_instance.vai_demo`
  seguido de `terraform apply`) para reprovisionar do zero.
- **Dados de exemplo**: como o cloud-init so roda no primeiro boot, a
  semeadura tambem so acontece nesse momento — reprovisionar do zero (item
  acima) gera um Postgres novo e semeia de novo automaticamente, mas um
  `docker compose up --build -d` manual sobre uma instancia ja provisionada
  nao. Nesse caso rode manualmente: `docker compose cp
  scripts/seed_demo_data.py api:/workspace/scripts/seed_demo_data.py &&
  docker compose exec api python scripts/seed_demo_data.py` (e seguro
  reexecutar — o script aborta sozinho se ja existirem iniciativas `[DEMO]`).
  A falha da semeadura nunca bloqueia o resto do provisionamento (e
  melhor-esforco, com aviso no log em vez de abortar).
- **Arquitetura**: a imagem usada e `ubuntu-2404-lts-amd64` (x86_64), ao
  contrario do modulo OCI que usa ARM64 - todas as imagens do
  `docker-compose.yml` (incluindo o ClamAV pinado por digest) tambem
  publicam manifesto `linux/amd64`, entao nao ha o mesmo risco de
  incompatibilidade de arquitetura que existe no modulo OCI.
