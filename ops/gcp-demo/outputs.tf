output "instance_public_ip" {
  value = google_compute_instance.vai_demo.network_interface[0].access_config[0].nat_ip
}

output "ssh_command" {
  value = "ssh -i <caminho-da-chave-privada> ${var.ssh_username}@${google_compute_instance.vai_demo.network_interface[0].access_config[0].nat_ip}"
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

output "next_step" {
  value = "Aponte ${var.app_domain} e ${var.api_domain} (DNS tipo A) para o IP acima. O cloud-init ja instala Docker, sobe o docker compose e configura o Caddy com TLS automatico + Basic Auth temporario."
}
