resource "google_compute_network" "vpc" {
  name                    = "vai-governance-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "vai-governance-public-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# Toda VPC do GCP ja tem uma regra implicita de allow-egress e deny-ingress -
# so precisamos abrir explicitamente o que a demo expoe.
resource "google_compute_firewall" "allow_http_https" {
  name    = "vai-governance-allow-http-https"
  network = google_compute_network.vpc.id

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["vai-governance-demo"]
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "vai-governance-allow-ssh"
  network = google_compute_network.vpc.id

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = [var.ssh_allowed_cidr]
  target_tags   = ["vai-governance-demo"]
}
