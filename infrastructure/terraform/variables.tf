variable "project_id" {
  description = "GCP project dedicated to this environment."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "environment must be development, staging, or production."
  }
}

variable "region" {
  description = "Primary GCP region."
  type        = string
  default     = "southamerica-east1"
}

variable "api_image" {
  description = "Immutable Artifact Registry image including an sha256 digest."
  type        = string
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.api_image))
    error_message = "api_image must be immutable and end with @sha256:<64 hex chars>."
  }
}

variable "firebase_project_id" {
  description = "Firebase Authentication project; defaults to the runtime GCP project."
  type        = string
  default     = null
  nullable    = true
}

variable "alert_email" {
  description = "Optional address for operational alerts."
  type        = string
  default     = null
  nullable    = true
}

variable "min_instances" {
  description = "Minimum warm Cloud Run instances. Production is forced to at least one."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Maximum Cloud Run instances."
  type        = number
  default     = 10
}

variable "paid_billing_enabled" {
  description = "Enable RevenueCat/Google Play billing for this environment."
  type        = bool
  default     = false
}

variable "free_beta_enabled" {
  description = "Enroll authenticated users into the server-authoritative free beta."
  type        = bool
  default     = true
}

variable "free_beta_allowance_seconds" {
  description = "Lifetime voice allowance assigned to each free-beta participant."
  type        = number
  default     = 7200
  validation {
    condition = (
      var.free_beta_allowance_seconds >= 600 &&
      var.free_beta_allowance_seconds <= 86400
    )
    error_message = "free_beta_allowance_seconds must be between 600 and 86400."
  }
}

variable "free_beta_max_accounts" {
  description = "Maximum number of accounts automatically enrolled in the free beta."
  type        = number
  default     = 30
  validation {
    condition = (
      var.free_beta_max_accounts >= 1 &&
      var.free_beta_max_accounts <= 1000
    )
    error_message = "free_beta_max_accounts must be between 1 and 1000."
  }
}
