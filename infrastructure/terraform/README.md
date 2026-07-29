# GCP runtime

This Terraform stack provisions the backend runtime in `southamerica-east1`:
Artifact Registry, a private VPC, Cloud SQL PostgreSQL, Memorystore Redis,
Secret Manager, a Cloud Run API, a one-shot Alembic migration job, and baseline
monitoring.

Terraform never creates secret values. Add versions for every secret after the
first apply and before deploying the API. In particular, `database-url` should
use the Cloud SQL private address and `redis-url` the Memorystore private
address. Production uses regional PostgreSQL, PITR, deletion protection, a
high-availability Redis tier, and at least one warm API instance.

The default access policy is a free beta: at most 30 authenticated accounts
receive a lifetime 120-minute voice allowance. RevenueCat secrets are not
created or mounted unless `paid_billing_enabled=true`; payment therefore is not
a prerequisite for the first usable cohort.

## State bootstrap

Create one versioned GCS state bucket outside this stack, enable uniform bucket
access and retention, then add this backend configuration locally:

```hcl
terraform {
  backend "gcs" {
    bucket = "YOUR_TERRAFORM_STATE_BUCKET"
    prefix = "english-sprint/ENVIRONMENT"
  }
}
```

Do not commit credentials or secret values. Authenticate with Application
Default Credentials and use an identity dedicated to infrastructure changes.

## Validate and deploy

```bash
docker run --rm -v "$PWD:/workspace" -w /workspace/infrastructure/terraform \
  hashicorp/terraform:1.14.5 fmt -check -recursive
docker run --rm -v "$PWD:/workspace" -w /workspace/infrastructure/terraform \
  hashicorp/terraform:1.14.5 init -backend=false
docker run --rm -v "$PWD:/workspace" -w /workspace/infrastructure/terraform \
  hashicorp/terraform:1.14.5 validate

terraform plan -var-file=environments/staging.tfvars
terraform apply -var-file=environments/staging.tfvars
gcloud run jobs execute english-sprint-staging-migrate \
  --region southamerica-east1 --wait
```

Use `environments/*.tfvars.example` as templates. Image references must be
immutable digests (`image@sha256:...`). Apply production only through an
approved plan and execute the migration job before shifting traffic.
