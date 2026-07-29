output "api_url" {
  description = "Cloud Run public API URL."
  value       = google_cloud_run_v2_service.api.uri
}

output "migration_job" {
  description = "Cloud Run job that applies Alembic migrations."
  value       = google_cloud_run_v2_job.migrate.name
}

output "postgres_private_address" {
  description = "Private Cloud SQL address used when preparing DATABASE_URL."
  value       = google_sql_database_instance.postgres.private_ip_address
}

output "redis_private_address" {
  description = "Private Redis address used when preparing REDIS_URL."
  value       = google_redis_instance.cache.host
}

output "runtime_secret_ids" {
  description = "Secret Manager resources requiring externally supplied versions."
  value       = { for key, secret in google_secret_manager_secret.runtime : key => secret.secret_id }
}
