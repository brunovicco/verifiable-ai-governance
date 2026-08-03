data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
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

resource "oci_core_instance" "vai_demo" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "vai-governance-demo"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gb
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.subnet.id
    assign_public_ip = true
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_size_gb
  }

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key_path)
    user_data = base64encode(templatefile("${path.module}/cloud-init.sh.tpl", {
      git_repo_url      = var.git_repo_url
      postgres_password = random_password.postgres.result
      minio_password    = random_password.minio.result
      audit_salt        = random_password.audit_salt.result
      app_domain        = var.app_domain
      api_domain        = var.api_domain
    }))
  }
}

# IP público reservado (fixo) -- opcional, evita que o IP mude se a instância
# for recriada. Se preferir o IP efêmero padrão, defina use_reserved_public_ip = false.
data "oci_core_vnic_attachments" "vai_demo_vnics" {
  compartment_id = var.compartment_ocid
  instance_id    = oci_core_instance.vai_demo.id
}

data "oci_core_vnic" "vai_demo_vnic" {
  vnic_id = data.oci_core_vnic_attachments.vai_demo_vnics.vnic_attachments[0].vnic_id
}

data "oci_core_private_ips" "vai_demo_private_ips" {
  vnic_id = data.oci_core_vnic.vai_demo_vnic.id
}

resource "oci_core_public_ip" "reserved" {
  count          = var.use_reserved_public_ip ? 1 : 0
  compartment_id = var.compartment_ocid
  lifetime       = "RESERVED"
  private_ip_id  = data.oci_core_private_ips.vai_demo_private_ips.private_ips[0].id
  display_name   = "vai-governance-reserved-ip"
}
