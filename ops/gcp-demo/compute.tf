data "google_compute_image" "ubuntu" {
  family  = "ubuntu-2404-lts-amd64"
  project = "ubuntu-os-cloud"
}

resource "random_password" "postgres" {
  length  = 24
  special = false
}

resource "random_password" "minio" {
  length  = 24
  special = false
}

resource "random_password" "audit_salt" {
  length  = 32
  special = false
}

# Service account dedicada para a instancia da demo, sem papeis de projeto
# adicionais -- so o escopo minimo de logging, para nao depender da service
# account default (com escopo de projeto amplo) do Compute Engine.
resource "google_service_account" "demo" {
  account_id   = "vai-governance-demo"
  display_name = "Verifiable AI Governance - demo instance"
}

# IP externo estatico -- opcional, evita que o IP mude se a instancia for
# recriada. Se preferir o IP efemero padrao, defina use_static_ip = false.
resource "google_compute_address" "static" {
  count  = var.use_static_ip ? 1 : 0
  name   = "vai-governance-static-ip"
  region = var.region
}

resource "google_compute_instance" "vai_demo" {
  name         = "vai-governance-demo"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["vai-governance-demo"]

  boot_disk {
    initialize_params {
      image = data.google_compute_image.ubuntu.self_link
      size  = var.boot_disk_size_gb
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id

    access_config {
      nat_ip = var.use_static_ip ? google_compute_address.static[0].address : null
    }
  }

  service_account {
    email  = google_service_account.demo.email
    scopes = ["https://www.googleapis.com/auth/logging.write"]
  }

  metadata = {
    ssh-keys = "${var.ssh_username}:${file(var.ssh_public_key_path)}"
    # A imagem Canonical do GCP roda cloud-init com o datasource GCE, que le
    # a chave de metadado "user-data" da mesma forma que AWS/OCI - o mesmo
    # cloud-init.sh.tpl usado no modulo OCI funciona aqui sem alteracoes.
    user-data = templatefile("${path.module}/cloud-init.sh.tpl", {
      git_repo_url      = var.git_repo_url
      git_ref           = var.git_ref
      postgres_password = random_password.postgres.result
      minio_password    = random_password.minio.result
      audit_salt        = random_password.audit_salt.result
      app_domain        = var.app_domain
      api_domain        = var.api_domain
    })
  }
}
