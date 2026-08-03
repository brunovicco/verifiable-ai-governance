# --- Autenticação OCI (gere em Profile -> API Keys no console, ou `oci setup keys`) ---
variable "tenancy_ocid" {
  type        = string
  description = "OCID do tenancy"
}

variable "user_ocid" {
  type        = string
  description = "OCID do usuário dono da API key"
}

variable "fingerprint" {
  type        = string
  description = "Fingerprint da API key"
}

variable "private_key_path" {
  type        = string
  description = "Caminho local da chave privada da API key (ex: ~/.oci/oci_api_key.pem)"
}

variable "region" {
  type        = string
  description = "Região OCI (ex: sa-saopaulo-1, us-ashburn-1)"
}

variable "compartment_ocid" {
  type        = string
  description = "OCID do compartment onde os recursos serão criados (pode ser o root do tenancy)"
}

# --- Acesso ---
variable "ssh_public_key_path" {
  type        = string
  description = "Caminho da chave pública SSH local"
  default     = "~/.ssh/oci-vai-demo.pub"
}

variable "ssh_allowed_cidr" {
  type        = string
  description = "CIDR autorizado a acessar a porta 22 (use SEU IP/32, nunca 0.0.0.0/0)"
}

# --- Shape ---
variable "instance_ocpus" {
  type        = number
  description = "OCPUs do Ampere A1 (confirme sua cota Always Free atual antes de mudar)"
  default     = 2
}

variable "instance_memory_gb" {
  type        = number
  description = "RAM em GB do Ampere A1"
  default     = 12
}

variable "boot_volume_size_gb" {
  type    = number
  default = 50
}

variable "use_reserved_public_ip" {
  type        = bool
  description = "Se true, associa um IP público reservado (fixo) em vez do efêmero padrão"
  default     = true
}

# --- Aplicação ---
variable "git_repo_url" {
  type    = string
  default = "https://github.com/brunovicco/verifiable-ai-governance.git"
}

variable "app_domain" {
  type        = string
  description = "Domínio público do portal (ex: app.seudominio.com). Aponte o DNS para o IP de saída deste apply antes de usar."
}

variable "api_domain" {
  type        = string
  description = "Domínio público da API (ex: api.seudominio.com)"
}

variable "basic_auth_user" {
  type        = string
  default     = "demo"
  description = "Usuário do Basic Auth temporário no Caddy (Opção A, antes do Entra ID entrar)"
}

variable "basic_auth_password" {
  type        = string
  sensitive   = true
  description = "Senha do Basic Auth temporário — defina via terraform.tfvars ou TF_VAR_basic_auth_password"
}
