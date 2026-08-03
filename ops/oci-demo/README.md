# IaC — Verifiable AI Governance no OCI Always Free

Terraform que provisiona **tudo**: VCN, subnet, security list, IP público
(reservado, opcional), a instância Ampere A1, e — via `cloud-init.sh.tpl` como
`user_data` — a configuração completa do SO (swap, firewall interno, Docker),
o clone do repositório, o `docker compose up` e o Caddy com TLS automático e
Basic Auth temporário. Um `terraform apply` deixa a demo no ar.

Um `terraform apply` deixa a demo no ar de ponta a ponta. Duas decisões ficam
de fora deste Terraform de propósito, por dependerem de contas/DNS fora da
infraestrutura provisionada aqui: a migração para Entra ID (ver
["Migrar para Entra ID depois"](#migrar-para-entra-id-depois)) e o registro
dos domínios no seu provedor de DNS.

## Pré-requisitos

0. **Conta OCI (Always Free)** — se ainda não tiver uma, crie em
   https://signup.oraclecloud.com. A ativação pode levar alguns minutos; é
   pedido um cartão só para validação de identidade, sem cobrança enquanto o
   uso ficar dentro dos limites Always Free (o shape usado aqui,
   `VM.Standard.A1.Flex`, é o compute ARM gratuito).
1. **Terraform** >= 1.6 instalado localmente.
2. **API signing key** da OCI — no Console: canto superior direito → seu
   usuário → **API Keys → Add API Key → Generate API Key Pair**. Baixe a chave
   privada e copie o fingerprint e a configuração exibida (tenancy OCID, user
   OCID, região) — essa mesma página do console já mostra os dois OCIDs
   prontos para colar no `terraform.tfvars`.
3. Um par de chaves SSH dedicado:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/oci-vai-demo -C "vai-demo"
   ```
4. Dois domínios/subdomínios (`app.` e `api.`) que você controla — só precisam
   apontar para o IP depois do apply, não antes. Se ainda não tiver um
   domínio, registre um em qualquer registrador antes de seguir — o `apply`
   funciona sem o DNS configurado, mas o Caddy só emite o certificado TLS
   depois que os registros tipo A apontarem para o IP publicado no final.

## Uso

```bash
cp terraform.tfvars.example terraform.tfvars
# edite terraform.tfvars com seus OCIDs, fingerprint, CIDR do seu IP, domínios, etc.

terraform init
terraform plan
terraform apply
```

Ao final, o Terraform imprime o IP público (reservado, se
`use_reserved_public_ip = true`). Aponte os registros DNS tipo A de
`app_domain` e `api_domain` para esse IP. O Caddy já está rodando e emite o
certificado Let's Encrypt automaticamente assim que o DNS propagar e a
primeira requisição chegar.

Recupere as credenciais geradas quando precisar:
```bash
terraform output postgres_password
terraform output minio_password
terraform output audit_hash_salt
```

## Migrar para Entra ID depois

Quando o Entra ID estiver pronto, os campos `OIDC_*` e `NEXT_PUBLIC_ENTRA_*`
ficam fora deste Terraform de propósito — são trocados direto no `.env` da VM
e exigem um rebuild do `web` (variáveis `NEXT_PUBLIC_*` são embutidas em
build-time). Não vale a pena automatizar isso agora porque muda uma vez só;
depois disso, entre via SSH na instância, edite `/opt/vai-governance/.env`
com os valores de `OIDC_ISSUER`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, os App
Registrations do Entra e os `NEXT_PUBLIC_ENTRA_*`, rode
`docker compose up --build -d` para aplicar o rebuild do `web`, e remova o
bloco `basic_auth` de `/etc/caddy/Caddyfile` (seguido de
`systemctl reload caddy`) já que a autenticação passa a ser feita pelo Entra
ID.

## Alternativa sem instalar Terraform localmente: OCI Resource Manager

Se preferir não gerenciar state do Terraform na sua máquina, o **Resource
Manager** da própria OCI roda este mesmo código nativamente, sem custo
adicional:

1. Compacte esta pasta (sem o `terraform.tfvars` preenchido) em um `.zip`.
2. Console → **Developer Services → Resource Manager → Stacks → Create Stack**
   → upload do `.zip`.
3. O assistente pede as mesmas variáveis do `terraform.tfvars.example` em um
   formulário.
4. **Plan** e depois **Apply** — o Resource Manager guarda o state por você.

Isso é IaC "puro OCI": nada roda fora da plataforma, e o histórico de
apply/destroy fica auditável no próprio Console.

## Observações importantes

- **Segredos no state**: `postgres_password`, `minio_password` e
  `audit_hash_salt` ficam no `terraform.tfstate` em texto plano (comportamento
  padrão do provider `random`). Para uma demo isso costuma ser aceitável, mas
  não versione o state em um repositório público — use um backend remoto
  (OCI Object Storage com criptografia, por exemplo) se isso importar para
  você.
- **Cota Always Free**: `instance_ocpus`/`instance_memory_gb` default para
  2/12, refletindo o corte de junho/2026. Se sua conta ainda mostrar 4 OCPU/24
  GB disponíveis, ajuste as variáveis livremente.
- **Idempotência do cloud-init**: o script roda uma única vez no primeiro
  boot. Para reaplicar mudanças de app (nova versão do repo, etc.), entre via
  SSH e rode `git pull && docker compose up --build -d` manualmente, ou
  destrua e reaplique a instância (`terraform taint oci_core_instance.vai_demo`
  seguido de `terraform apply`) para reprovisionar do zero.
- **Arquitetura ARM64**: a instância é Ampere A1 (aarch64). Todas as imagens
  usadas pelo `docker-compose.yml` publicam manifesto multi-arch com suporte a
  `linux/arm64` — incluindo `clamav/clamav-debian:1.4.5@sha256:...`, a única
  fixada por digest (confirmado via `docker manifest inspect`). Se esse
  digest for atualizado no futuro, vale reconfirmar com o mesmo comando antes
  do `apply`, procurando `linux/arm64` na lista de plataformas — se não
  resolver, o `docker compose build` falha no cloud-init e a demo não sobe;
  verifique `/var/log/vai-cloud-init.log` via SSH nesse caso. O cloud-init só
  grava `/opt/vai-governance/.cloud-init-done` quando termina com sucesso.
