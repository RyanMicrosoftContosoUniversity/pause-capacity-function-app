terraform {
  # >= 1.6 for the `test` command and import blocks; pinned upper bound avoids
  # a surprise major upgrade breaking the pipeline.
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      # azurerm_fabric_capacity landed in 4.4.0.
      version = "~> 4.14"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.6"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }

  # Backend is configured per environment by the pipeline:
  #   terraform init -backend-config=backends/<env>.hcl
  backend "azurerm" {}
}

provider "azurerm" {
  subscription_id = var.subscription_id

  features {
    resource_group {
      # The pause app's resource groups hold alert rules created outside
      # Terraform. Refusing to delete a non-empty RG is the safer default.
      prevent_deletion_if_contains_resources = true
    }
  }
}

data "azurerm_client_config" "current" {}
