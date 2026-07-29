locals {
  name          = "english-sprint-${var.environment}"
  is_production = var.environment == "production"
  labels = {
    app         = "english-sprint"
    environment = var.environment
    managed_by  = "terraform"
  }
  services = toset([
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "redis.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "vpcaccess.googleapis.com",
  ])
  secret_names = toset(concat(
    [
      "database-url",
      "redis-url",
      "openai-api-key",
      "installation-hash-secret",
      "content-encryption-key",
      "internal-api-token",
    ],
    var.paid_billing_enabled ? [
      "revenuecat-api-key",
      "revenuecat-webhook-token",
    ] : [],
  ))
}

resource "google_project_service" "required" {
  for_each           = local.services
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "backend" {
  location      = var.region
  repository_id = local.name
  description   = "Immutable English Sprint backend images"
  format        = "DOCKER"
  labels        = local.labels
  depends_on    = [google_project_service.required]
}

resource "google_compute_network" "private" {
  name                    = "${local.name}-network"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.required]
}

resource "google_compute_subnetwork" "private" {
  name                     = "${local.name}-subnet"
  region                   = var.region
  network                  = google_compute_network.private.id
  ip_cidr_range            = "10.42.0.0/24"
  private_ip_google_access = true
}

resource "google_compute_global_address" "service_range" {
  name          = "${local.name}-service-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.private.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.private.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.service_range.name]
  depends_on              = [google_project_service.required]
}

resource "google_vpc_access_connector" "serverless" {
  name          = "${local.name}-connector"
  region        = var.region
  network       = google_compute_network.private.name
  ip_cidr_range = "10.42.8.0/28"
  min_instances = 2
  max_instances = 3
  depends_on    = [google_project_service.required]
}

resource "google_sql_database_instance" "postgres" {
  name             = "${local.name}-postgres"
  region           = var.region
  database_version = "POSTGRES_17"

  settings {
    tier              = local.is_production ? "db-custom-2-7680" : "db-custom-1-3840"
    availability_type = local.is_production ? "REGIONAL" : "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = local.is_production ? 50 : 20
    disk_autoresize   = true
    user_labels       = local.labels

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = local.is_production ? 14 : 7
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.private.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
  }

  deletion_protection = local.is_production
  depends_on          = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "application" {
  name     = "english_sprint"
  instance = google_sql_database_instance.postgres.name
}

resource "google_redis_instance" "cache" {
  name               = "${local.name}-redis"
  region             = var.region
  tier               = local.is_production ? "STANDARD_HA" : "BASIC"
  memory_size_gb     = 1
  redis_version      = "REDIS_7_2"
  authorized_network = google_compute_network.private.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  labels             = local.labels
  depends_on         = [google_service_networking_connection.private_services]
}

resource "google_secret_manager_secret" "runtime" {
  for_each  = local.secret_names
  secret_id = "${local.name}-${each.value}"
  labels    = local.labels

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
  depends_on = [google_project_service.required]
}

resource "google_service_account" "api" {
  account_id   = "es-${substr(var.environment, 0, 8)}-api"
  display_name = "English Sprint ${var.environment} API"
}

resource "google_project_iam_member" "api_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/firebaseauth.admin",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_secret_access" {
  for_each  = google_secret_manager_secret.runtime
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name                = "${local.name}-api"
  location            = var.region
  deletion_protection = local.is_production
  ingress             = "INGRESS_TRAFFIC_ALL"
  labels              = local.labels

  template {
    service_account                  = google_service_account.api.email
    timeout                          = "3600s"
    max_instance_request_concurrency = 20

    scaling {
      min_instance_count = local.is_production ? max(1, var.min_instances) : var.min_instances
      max_instance_count = var.max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.serverless.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle = false
      }

      env {
        name  = "APP_ENV"
        value = var.environment
      }
      env {
        name  = "AUTH_ENABLED"
        value = "true"
      }
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = coalesce(var.firebase_project_id, var.project_id)
      }
      env {
        name  = "REALTIME_ENABLED"
        value = "true"
      }
      env {
        name  = "PEDAGOGY_ENABLED"
        value = "true"
      }
      env {
        name  = "BILLING_ENABLED"
        value = tostring(var.paid_billing_enabled)
      }
      env {
        name  = "FREE_BETA_ENABLED"
        value = tostring(var.free_beta_enabled)
      }
      env {
        name  = "FREE_BETA_ALLOWANCE_SECONDS"
        value = tostring(var.free_beta_allowance_seconds)
      }
      env {
        name  = "FREE_BETA_MAX_ACCOUNTS"
        value = tostring(var.free_beta_max_accounts)
      }
      env {
        name  = "CONTENT_RETENTION_ENABLED"
        value = "false"
      }
      env {
        name  = "CONTENT_ENCRYPTION_KEY_VERSION"
        value = "v1"
      }

      dynamic "env" {
        for_each = merge({
          DATABASE_URL             = "database-url"
          REDIS_URL                = "redis-url"
          OPENAI_API_KEY           = "openai-api-key"
          INSTALLATION_HASH_SECRET = "installation-hash-secret"
          CONTENT_ENCRYPTION_KEY   = "content-encryption-key"
          INTERNAL_API_TOKEN       = "internal-api-token"
          }, var.paid_billing_enabled ? {
          REVENUECAT_SECRET_API_KEY = "revenuecat-api-key"
          REVENUECAT_WEBHOOK_SECRET = "revenuecat-webhook-token"
        } : {})
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.runtime[env.value].secret_id
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        failure_threshold     = 20
        initial_delay_seconds = 5
        period_seconds        = 3
        timeout_seconds       = 2
        http_get {
          path = "/healthz"
          port = 8080
        }
      }

      liveness_probe {
        failure_threshold = 3
        period_seconds    = 30
        timeout_seconds   = 2
        http_get {
          path = "/healthz"
          port = 8080
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.api_roles,
    google_secret_manager_secret_iam_member.api_secret_access,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_api" {
  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_job" "migrate" {
  name                = "${local.name}-migrate"
  location            = var.region
  deletion_protection = local.is_production
  labels              = local.labels

  template {
    template {
      service_account = google_service_account.api.email
      timeout         = "900s"
      max_retries     = 1

      vpc_access {
        connector = google_vpc_access_connector.serverless.id
        egress    = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image   = var.api_image
        command = ["/app/backend/.venv/bin/alembic"]
        args    = ["upgrade", "head"]
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.runtime["database-url"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
}

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == null ? 0 : 1
  display_name = "${local.name} operator email"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_monitoring_uptime_check_config" "readiness" {
  display_name = "${local.name} readiness"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path           = "/readyz"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      host       = trimprefix(google_cloud_run_v2_service.api.uri, "https://")
      project_id = var.project_id
    }
  }
}

resource "google_monitoring_alert_policy" "readiness" {
  display_name = "${local.name} readiness unavailable"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Readiness check failing"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\""
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "180s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }

  notification_channels = [
    for channel in google_monitoring_notification_channel.email : channel.name
  ]
}
