output "instance_ephemeral_public_ip" {
  value = oci_core_instance.vai_demo.public_ip
}

output "instance_reserved_public_ip" {
  value = var.use_reserved_public_ip ? oci_core_public_ip.reserved[0].ip_address : null
}

output "ssh_command" {
  value = "ssh -i <caminho-da-chave-privada> ubuntu@${var.use_reserved_public_ip ? oci_core_public_ip.reserved[0].ip_address : oci_core_instance.vai_demo.public_ip}"
}

output "postgres_password" {
  value     = random_password.postgres.result
  sensitive = true
}

output "minio_password" {
  value     = random_password.minio.result
  sensitive = true
}

output "audit_hash_salt" {
  value     = random_password.audit_salt.result
  sensitive = true
}

output "requested_git_ref" {
  value       = var.git_ref
  description = "Tag/branch/SHA solicitado ao Terraform para este deploy. O SHA curto efetivamente resolvido pelo cloud-init aparece no rodapé do portal (NEXT_PUBLIC_GIT_SHA) após o provisionamento."
}

output "next_step" {
  value = "Aponte ${var.app_domain} e ${var.api_domain} (DNS tipo A) para o IP acima. O cloud-init já instala Docker, sobe o docker compose e configura o Caddy com TLS automático (demo pública somente leitura, sem credencial)."
}
