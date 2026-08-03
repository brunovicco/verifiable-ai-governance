# --- Autenticacao GCP ---
# A autenticacao usa Application Default Credentials (gcloud auth
# application-default login) - nenhuma variavel de credencial aqui de
# proposito. Veja o README para o passo a passo.
variable "project_id" {
  type        = string
  description = "ID do projeto GCP (nao o nome de exibicao) onde os recursos serao criados"
}

variable "region" {
  type        = string
  description = "Regiao GCP (ex: us-central1, southamerica-east1)"
  default     = "us-central1"
}

variable "zone" {
  type        = string
  description = "Zona GCP dentro da regiao (ex: us-central1-a)"
  default     = "us-central1-a"
}

# --- Acesso ---
variable "ssh_public_key_path" {
  type        = string
  description = "Caminho da chave publica SSH local"
  default     = "~/.ssh/gcp-vai-demo.pub"
}

variable "ssh_username" {
  type        = string
  description = "Usuario Linux associado a chave SSH (o cloud-init assume 'ubuntu', o usuario padrao da imagem Canonical)"
  default     = "ubuntu"
}

variable "ssh_allowed_cidr" {
  type        = string
  description = "CIDR autorizado a acessar a porta 22 (use SEU IP/32, nunca 0.0.0.0/0)"
}

# --- Maquina ---
variable "machine_type" {
  type        = string
  description = "Machine type do Compute Engine (e2-standard-2 = 2 vCPU/8GB, cabe folgado no credito de US$300/90 dias de conta nova)"
  default     = "e2-standard-2"
}

variable "boot_disk_size_gb" {
  type    = number
  default = 50
}

variable "use_static_ip" {
  type        = bool
  description = "Se true, reserva um IP externo estatico em vez do efemero padrao"
  default     = true
}

# --- Aplicacao ---
variable "git_repo_url" {
  type    = string
  default = "https://github.com/brunovicco/verifiable-ai-governance.git"
}

variable "git_ref" {
  type        = string
  description = "Tag, branch ou commit SHA a implantar (default: HEAD do branch main). Fixe em uma tag/SHA para deploys reproduziveis."
  default     = "main"
}

variable "app_domain" {
  type        = string
  description = "Dominio publico do portal (ex: app.seudominio.com). Aponte o DNS para o IP de saida deste apply antes de usar."
}

variable "api_domain" {
  type        = string
  description = "Dominio publico da API (ex: api.seudominio.com)"
}
