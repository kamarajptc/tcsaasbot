# Tenant Registry Schema and IaC Structure

This document defines:
- an exact tenant registry schema for dual-cloud deployment (`AWS` for enterprise, `DigitalOcean` for MSME),
- migration notes from the current `tenants` table in this repo,
- a concrete IaC folder structure for implementation.

## 1) Target Tenant Registry (PostgreSQL)

Use PostgreSQL for control-plane metadata, even if data-plane differs by tenant.

```sql
-- Recommended extension for UUID generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Optional enums (can be TEXT + CHECK if preferred)
DO $$ BEGIN
  CREATE TYPE tenant_plan AS ENUM ('starter', 'pro', 'enterprise');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE tenant_status AS ENUM ('active', 'suspended', 'terminated');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE cloud_provider AS ENUM ('aws', 'digitalocean');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE deployment_tier AS ENUM ('enterprise_aws', 'msme_do');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE auth_provider AS ENUM ('cognito', 'internal_jwt');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS tenant_registry (
  tenant_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_key             VARCHAR(120) NOT NULL UNIQUE, -- stable external key (e.g. ops@acme.com)
  tenant_name            VARCHAR(200) NOT NULL,
  plan                   tenant_plan NOT NULL DEFAULT 'starter',
  status                 tenant_status NOT NULL DEFAULT 'active',
  deployment_tier        deployment_tier NOT NULL,
  cloud_provider         cloud_provider NOT NULL,
  primary_region         VARCHAR(50) NOT NULL,         -- e.g. us-east-1, nyc3
  auth_provider          auth_provider NOT NULL,
  data_residency         VARCHAR(50) NULL,             -- e.g. US, IN, EU
  billing_customer_id    VARCHAR(120) NULL,
  tags_json              JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  terminated_at          TIMESTAMPTZ NULL,
  CHECK (
    (deployment_tier = 'enterprise_aws' AND cloud_provider = 'aws')
    OR
    (deployment_tier = 'msme_do' AND cloud_provider = 'digitalocean')
  )
);

CREATE INDEX IF NOT EXISTS idx_tenant_registry_status ON tenant_registry(status);
CREATE INDEX IF NOT EXISTS idx_tenant_registry_provider_region ON tenant_registry(cloud_provider, primary_region);
CREATE INDEX IF NOT EXISTS idx_tenant_registry_plan ON tenant_registry(plan);
CREATE INDEX IF NOT EXISTS idx_tenant_registry_tags_gin ON tenant_registry USING GIN(tags_json);

CREATE TABLE IF NOT EXISTS tenant_runtime_config (
  tenant_id              UUID PRIMARY KEY REFERENCES tenant_registry(tenant_id) ON DELETE CASCADE,
  api_base_url           VARCHAR(255) NOT NULL,        -- gateway-routed endpoint
  chat_service_url       VARCHAR(255) NOT NULL,
  ingest_service_url     VARCHAR(255) NOT NULL,
  analytics_service_url  VARCHAR(255) NOT NULL,
  vector_store_type      VARCHAR(40) NOT NULL,         -- chroma|qdrant|pgvector
  vector_store_endpoint  VARCHAR(255) NULL,
  object_store_type      VARCHAR(40) NOT NULL,         -- s3|spaces
  object_store_bucket    VARCHAR(120) NOT NULL,
  db_host                VARCHAR(255) NOT NULL,
  db_name                VARCHAR(120) NOT NULL,
  db_schema              VARCHAR(80) NOT NULL DEFAULT 'public',
  kms_key_ref            VARCHAR(255) NULL,
  config_version         INTEGER NOT NULL DEFAULT 1,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant_identity_config (
  tenant_id              UUID PRIMARY KEY REFERENCES tenant_registry(tenant_id) ON DELETE CASCADE,
  cognito_user_pool_id   VARCHAR(120) NULL,
  cognito_app_client_id  VARCHAR(120) NULL,
  cognito_region         VARCHAR(50) NULL,
  jwt_issuer             VARCHAR(255) NULL,
  jwt_audience           VARCHAR(255) NULL,
  sso_enabled            BOOLEAN NOT NULL DEFAULT FALSE,
  sso_metadata_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (cognito_user_pool_id IS NOT NULL AND cognito_app_client_id IS NOT NULL)
    OR
    (jwt_issuer IS NOT NULL AND jwt_audience IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS tenant_deployments (
  deployment_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id              UUID NOT NULL REFERENCES tenant_registry(tenant_id) ON DELETE CASCADE,
  environment            VARCHAR(20) NOT NULL,         -- dev|staging|prod
  provider               cloud_provider NOT NULL,
  region                 VARCHAR(50) NOT NULL,
  stack_name             VARCHAR(180) NOT NULL,
  image_tag              VARCHAR(120) NOT NULL,
  release_sha            VARCHAR(64) NOT NULL,
  status                 VARCHAR(20) NOT NULL,         -- provisioning|healthy|failed|draining
  output_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, environment)
);

CREATE INDEX IF NOT EXISTS idx_tenant_deployments_status ON tenant_deployments(status);
CREATE INDEX IF NOT EXISTS idx_tenant_deployments_provider ON tenant_deployments(provider, region);
```

### Trigger for `updated_at`

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tenant_registry_updated_at ON tenant_registry;
CREATE TRIGGER trg_tenant_registry_updated_at
BEFORE UPDATE ON tenant_registry
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_runtime_config_updated_at ON tenant_runtime_config;
CREATE TRIGGER trg_tenant_runtime_config_updated_at
BEFORE UPDATE ON tenant_runtime_config
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_identity_config_updated_at ON tenant_identity_config;
CREATE TRIGGER trg_tenant_identity_config_updated_at
BEFORE UPDATE ON tenant_identity_config
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_deployments_updated_at ON tenant_deployments;
CREATE TRIGGER trg_tenant_deployments_updated_at
BEFORE UPDATE ON tenant_deployments
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

## 2) Migration Mapping from Current Repo

Current table in repo: `backend/app/core/database.py -> TenantDB` with fields:
- `id`, `name`, `plan`, `is_active`, `stripe_customer_id`, `stripe_subscription_id`, `created_at`

Map as:
- `tenants.id` -> `tenant_registry.tenant_key`
- `tenants.name` -> `tenant_registry.tenant_name`
- `tenants.plan` -> `tenant_registry.plan`
- `tenants.is_active` -> `tenant_registry.status` (`true=active`, `false=suspended`)
- `tenants.stripe_customer_id` -> `tenant_registry.billing_customer_id`
- `tenant_registry.deployment_tier`:
  - `enterprise` plan -> `enterprise_aws`
  - otherwise -> `msme_do`
- `tenant_registry.cloud_provider`:
  - `enterprise` plan -> `aws`
  - otherwise -> `digitalocean`

Initial migration SQL:

```sql
INSERT INTO tenant_registry (
  tenant_key, tenant_name, plan, status, deployment_tier, cloud_provider, primary_region, auth_provider, billing_customer_id, created_at
)
SELECT
  t.id,
  COALESCE(NULLIF(t.name, ''), t.id),
  CASE WHEN t.plan IN ('starter','pro','enterprise') THEN t.plan::tenant_plan ELSE 'starter'::tenant_plan END,
  CASE WHEN t.is_active THEN 'active'::tenant_status ELSE 'suspended'::tenant_status END,
  CASE WHEN t.plan = 'enterprise' THEN 'enterprise_aws'::deployment_tier ELSE 'msme_do'::deployment_tier END,
  CASE WHEN t.plan = 'enterprise' THEN 'aws'::cloud_provider ELSE 'digitalocean'::cloud_provider END,
  CASE WHEN t.plan = 'enterprise' THEN 'us-east-1' ELSE 'nyc3' END,
  CASE WHEN t.plan = 'enterprise' THEN 'cognito'::auth_provider ELSE 'internal_jwt'::auth_provider END,
  t.stripe_customer_id,
  COALESCE(t.created_at, now())
FROM tenants t
ON CONFLICT (tenant_key) DO NOTHING;
```

## 3) IaC Folder Structure (Terraform)

Create this at repo root:

```text
infra/
  README.md
  scripts/
    tf_fmt_validate.sh
    plan_all.sh
    apply_tenant.sh
  environments/
    shared/
      backend.hcl
      providers.tf
      versions.tf
      variables.tf
      outputs.tf
    aws-enterprise/
      us-east-1/
        terragrunt.hcl
        tenant.auto.tfvars.json
      eu-west-1/
        terragrunt.hcl
        tenant.auto.tfvars.json
    do-msme/
      nyc3/
        terragrunt.hcl
        tenant.auto.tfvars.json
      blr1/
        terragrunt.hcl
        tenant.auto.tfvars.json
  modules/
    common/
      naming/
        main.tf
        variables.tf
        outputs.tf
      tags/
        main.tf
        variables.tf
        outputs.tf
      observability/
        main.tf
        variables.tf
        outputs.tf
      secrets_contract/
        main.tf
        variables.tf
        outputs.tf
    aws/
      network/
      rds_postgres/
      s3_storage/
      cognito_auth/
      ecs_service/
      lambda_api/
      sqs_queue/
      cloudwatch/
      api_gateway/
    do/
      project/
      vpc/
      managed_postgres/
      spaces_storage/
      app_platform_service/
      functions_api/
      redis_cache/
      load_balancer/
  stacks/
    control-plane/
      main.tf
      variables.tf
      outputs.tf
    data-plane-aws/
      main.tf
      variables.tf
      outputs.tf
    data-plane-do/
      main.tf
      variables.tf
      outputs.tf
```

## 4) Minimal Variables Contract (for both providers)

`infra/stacks/*/variables.tf` should share:

```hcl
variable "tenant_key"         { type = string }
variable "tenant_name"        { type = string }
variable "deployment_tier"    { type = string } # enterprise_aws | msme_do
variable "cloud_provider"     { type = string } # aws | digitalocean
variable "region"             { type = string }
variable "environment"        { type = string } # dev | staging | prod
variable "plan"               { type = string } # starter | pro | enterprise
variable "image_tag"          { type = string }
variable "release_sha"        { type = string }
variable "tags"               { type = map(string) }
```

## 5) Execution Model

1. Control plane reads `tenant_registry`.
2. It selects stack by `deployment_tier`.
3. It applies either:
   - `stacks/data-plane-aws` for `enterprise_aws`
   - `stacks/data-plane-do` for `msme_do`
4. It writes resulting endpoints/ids into:
   - `tenant_runtime_config`
   - `tenant_identity_config`
   - `tenant_deployments`

This keeps one product codebase while isolating infra per tenant segment.

