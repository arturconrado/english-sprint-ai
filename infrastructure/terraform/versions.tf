terraform {
  required_version = "= 1.14.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 7.41.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
