# FSI GECX Bundle Top-Level Makefile
# Integrates banking-service, banking-ui, adk-agent, and Terraform deployment workflows.

PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null || echo "YOUR_PROJECT_ID")
PROJECT_NUMBER ?= $(shell gcloud projects describe $(PROJECT_ID) --format="value(projectNumber)" 2>/dev/null || echo "YOUR_PROJECT_NUMBER")
REGION ?= us-central1
DOCKER ?= podman
CONTAINER_RUNTIME ?= $(shell bash scripts/dev/container-runtime.sh 2>/dev/null || echo "docker")
LIVEKIT_SERVER_VERSION ?= v1.13.1
FRONTEND_PORT ?= 5173
TF_VARS ?= ./environment/$(PROJECT_ID)/terraform.tfvars
TF_BACKEND ?= ./environment/$(PROJECT_ID)/gcs.tfbackend
CUSTOM_DOMAIN ?= $(shell grep -E '^[[:space:]]*custom_domain[[:space:]]*=[[:space:]]*' deployment/terraform/$(TF_VARS) 2>/dev/null | cut -d'=' -f2 | tr -d ' "[:space:]' || echo "banking.erikvoit.demo.altostrat.com")
DATA_STORE_ID ?= $(shell grep -E '^[[:space:]]*data_store_id[[:space:]]*=[[:space:]]*' deployment/terraform/discovery_engine.tf 2>/dev/null | cut -d'"' -f2 || echo "banking-site_1778875783412")
GCP_ACCOUNT ?= $(shell ACCOUNT=$$(gcloud config get-value account 2>/dev/null); echo "$${ACCOUNT%.gserviceaccount.com}")
GCP_ACCOUNT_ENCODED = $(subst @,%40,$(GCP_ACCOUNT))


.PHONY: help
help: ## Display available commands and their descriptions
	@echo "======================================================================"
	@echo "                      FSI GECX Bundle Makefile                        "
	@echo "======================================================================"
	@echo "Available commands:"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Bootstrap dependencies for the backend, voice agent, and frontend
	@echo "Installing banking-service dependencies..."
	cd banking-service && uv sync --frozen
	@echo "Installing credit-support-agent dependencies..."
	cd adk-agent/credit-support-agent && uv sync --frozen
	@echo "Installing banking-ui dependencies..."
	cd banking-ui && npm install

.PHONY: compile-deps
compile-deps: ## Lock banking-service dependencies using uv
	@echo "Locking banking-service dependencies..."
	cd banking-service && uv lock

.PHONY: setup
setup: install ## Alias for make install

.PHONY: build
build: ## Build the banking-ui production bundle
	@echo "Building banking-ui production bundle..."
	cd banking-ui && npm run build

.PHONY: test
test: ## Run backend unit tests via pytest
	@echo "Running banking-service tests..."
	cd banking-service && uv run pytest

.PHONY: shadow-db-up
shadow-db-up: ## Start the local-only PostgreSQL shadow DB for Alembic work
	@CONTAINER_RUNTIME="$(CONTAINER_RUNTIME)" bash scripts/dev/alembic-shadow.sh up

.PHONY: shadow-db-down
shadow-db-down: ## Stop the local-only PostgreSQL shadow DB
	@CONTAINER_RUNTIME="$(CONTAINER_RUNTIME)" bash scripts/dev/alembic-shadow.sh down

.PHONY: livekit-up
livekit-up: ## Start the local LiveKit server container
	@echo "Starting LiveKit server..."
	@$(CONTAINER_RUNTIME) rm -f livekit-server-dev 2>/dev/null || true
	$(CONTAINER_RUNTIME) run -d --name livekit-server-dev -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server:$(LIVEKIT_SERVER_VERSION) --dev --keys "devkey: secret" --node-ip 127.0.0.1 --rtc.enable_loopback_candidate

.PHONY: livekit-down
livekit-down: ## Stop the local LiveKit server container
	@echo "Stopping LiveKit server..."
	$(CONTAINER_RUNTIME) rm -f livekit-server-dev

.PHONY: shadow-db-logs
shadow-db-logs: ## Tail logs for the local-only PostgreSQL shadow DB
	@CONTAINER_RUNTIME="$(CONTAINER_RUNTIME)" bash scripts/dev/alembic-shadow.sh logs

.PHONY: alembic-shadow-current
alembic-shadow-current: ## Show Alembic current revision against the local shadow DB
	@CONTAINER_RUNTIME="$(CONTAINER_RUNTIME)" bash scripts/dev/alembic-shadow.sh current

.PHONY: alembic-shadow-upgrade
alembic-shadow-upgrade: ## Run alembic upgrade head against the local shadow DB
	@CONTAINER_RUNTIME="$(CONTAINER_RUNTIME)" bash scripts/dev/alembic-shadow.sh upgrade

.PHONY: alembic-shadow-revision
alembic-shadow-revision: ## Autogenerate an Alembic revision against the local shadow DB (usage: make alembic-shadow-revision MESSAGE="add foo")
	@if [ -z "$(MESSAGE)" ]; then echo "Error: MESSAGE is required. Usage: make alembic-shadow-revision MESSAGE=\"add foo\""; exit 1; fi
	@CONTAINER_RUNTIME="$(CONTAINER_RUNTIME)" bash scripts/dev/alembic-shadow.sh revision "$(MESSAGE)"

.PHONY: db-revision
db-revision: ## Preferred local flow: start shadow DB, upgrade head, and autogenerate a revision (usage: make db-revision MESSAGE="add foo")
	@if [ -z "$(MESSAGE)" ]; then echo "Error: MESSAGE is required. Usage: make db-revision MESSAGE=\"add foo\""; exit 1; fi
	@CONTAINER_RUNTIME="$(CONTAINER_RUNTIME)" bash scripts/dev/alembic-shadow.sh revision "$(MESSAGE)"

.PHONY: test-integration
test-integration: ## Execute live GCP sandbox Document AI integration tests (manually triggered)
	@echo "Executing live cloud sandbox integration test suite..."
	cd banking-service && RUN_INTEGRATION_TESTS=true .venv/bin/pytest tests/test_integration_docai.py -v -s

.PHONY: db-init-local
db-init-local: ## Initialize and seed the local SQLite database
	@echo "Initializing and seeding local SQLite database..."
	cd banking-service && uv run python -m services.seeding_service

.PHONY: run-backend-local
run-backend-local: ## Run the FastAPI banking service locally
	@echo "Starting banking-service..."
	cd banking-service && VOICE_AGENT_SERVICE_URL=http://localhost:8088 FULL_RESET_ENABLED=true DATABASE_IAM_SUPPORT_USERS=$(GCP_ACCOUNT) FULL_RESET_OPERATOR_EMAILS=$(GCP_ACCOUNT) uv run uvicorn main:app --host "0.0.0.0" --port 8080 --reload

.PHONY: run-backend-iam
run-backend-iam: ## Run the FastAPI banking service locally
	@echo "Starting banking-service..."
	cd banking-service && VOICE_AGENT_SERVICE_URL=http://localhost:8088 FULL_RESET_ENABLED=true DATABASE_IAM_SUPPORT_USERS=$(GCP_ACCOUNT) FULL_RESET_OPERATOR_EMAILS=$(GCP_ACCOUNT) DB_IAM_AUTH=true DATABASE_URL="postgresql+psycopg2://$(GCP_ACCOUNT_ENCODED)@localhost:5432/banking?sslmode=disable" uv run uvicorn main:app --host "0.0.0.0" --port 8080 --reload

.PHONY: run-frontend
run-frontend: ## Run the React/Vite frontend dev server locally
	@echo "Starting banking-ui dev server..."
	@if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:$(FRONTEND_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "Error: frontend port $(FRONTEND_PORT) is already in use. Stop the other process or run with FRONTEND_PORT=<port>."; \
		exit 1; \
	fi
	cd banking-ui && PROJECT_ID=$(PROJECT_ID) npm run dev -- --host localhost --port $(FRONTEND_PORT) --strictPort

.PHONY: run-data-generator
run-data-generator: ## Run the FastAPI synthetic data generator locally
	@echo "Starting data-generator..."
	cd data-generator && PROJECT_ID=$(PROJECT_ID) ./run.sh

.PHONY: run-voice-agent
run-voice-agent: ## Run the credit card support voice agent locally
	@echo "Starting credit-support-agent..."
	cd adk-agent/credit-support-agent && PORT=8088 BANKING_SERVICE_URL=http://localhost:8080 VOICE_AGENT_AUDIO_MODEL="publishers/google/models/gemini-live-2.5-flash-native-audio" VOICE_AGENT_VIDEO_MODEL="publishers/google/models/gemini-live-2.5-flash-native-audio" uv run --frozen python voice_agent.py

.PHONY: run-local
run-local: livekit-up ## Start LiveKit, the local backend, frontend, and voice agent
	@echo "Starting local backend, frontend, and voice agent concurrently... Press Ctrl+C to stop."
	@$(MAKE) -j3 run-backend-local run-frontend run-voice-agent

.PHONY: run
run: ## Concurrently run both backend and frontend servers locally
	@echo "Starting backend and frontend concurrently... Press Ctrl+C to stop."
	@trap 'kill 0' SIGINT; \
	$(MAKE) run-backend-iam & \
	$(MAKE) run-frontend & \
	wait

.PHONY: tf-init
tf-init: ## Initialize Terraform (accepts optional arguments, e.g., make tf-init ARGS="--reconfigure")
	cd deployment/terraform && \
	terraform init -backend-config=$(TF_BACKEND) $(ARGS)

.PHONY: tf-plan
tf-plan: ## Compute and display the incremental Terraform deployment diff
	@echo "Planning Terraform deployment diff..."
	cd deployment/terraform && \
	terraform plan -var-file $(TF_VARS) -out=tfplan

.PHONY: tf-fmt
tf-fmt: ## Format Terraform configuration files
	@echo "Formatting Terraform configuration files..."
	cd deployment/terraform && \
	terraform fmt

.PHONY: deploy
deploy: ## Safely apply the incremental Terraform deployment changes
	@echo "Applying incremental Terraform deployment..."
	cd deployment/terraform && \
	terraform apply tfplan

.PHONY: deploy-voice-agent
deploy-voice-agent: ## Submit Cloud Build job to deploy ADK credit-support-agent (voice agent) to Cloud Run
	@echo "Submitting Cloud Build job for credit-support-agent deployment..."
	gcloud builds submit --config adk-agent/credit-support-agent/cloudbuild-deploy.yaml --substitutions=_TRIGGER_DEPLOY=true

.PHONY: deploy-target
deploy-target: ## Deploy an isolated Terraform resource/module (usage: make deploy-target TARGET=module.foo)
	@if [ -z "$(TARGET)" ]; then echo "Error: TARGET is required. Usage: make deploy-target TARGET=module.foo"; exit 1; fi
	@echo "Applying targeted deployment for $(TARGET)..."
	cd deployment/terraform && \
	terraform apply -var-file ./terraform.tfvars -target=$(TARGET)

.PHONY: publish-images
publish-images: ## Build and push local container images to Artifact Registry
	@echo "Building and pushing banking-service image..."
	cd banking-service && docker build -t "$(REGION)-docker.pkg.dev/$(PROJECT_ID)/fsi-gecx-bundle/banking-service:latest" .
	docker push "$(REGION)-docker.pkg.dev/$(PROJECT_ID)/fsi-gecx-bundle/banking-service:latest"
	@echo "Building and pushing banking-ui image..."
	cd banking-ui && docker build -t "$(REGION)-docker.pkg.dev/$(PROJECT_ID)/fsi-gecx-bundle/banking-ui:latest" .
	docker push "$(REGION)-docker.pkg.dev/$(PROJECT_ID)/fsi-gecx-bundle/banking-ui:latest"
	@echo "Building and pushing data-generator image..."
	cd data-generator && docker build -t "$(REGION)-docker.pkg.dev/$(PROJECT_ID)/fsi-gecx-bundle/data-generator:latest" .
	docker push "$(REGION)-docker.pkg.dev/$(PROJECT_ID)/fsi-gecx-bundle/data-generator:latest"
	@echo "Building and pushing credit-support-agent image..."
	docker build -f adk-agent/credit-support-agent/Dockerfile -t "$(REGION)-docker.pkg.dev/$(PROJECT_ID)/fsi-gecx-bundle/credit-support-agent:latest" .
	docker push "$(REGION)-docker.pkg.dev/$(PROJECT_ID)/fsi-gecx-bundle/credit-support-agent:latest"

.PHONY: publish-images-cloud
publish-images-cloud: ## Submit Cloud Build jobs using official publish/deploy YAMLs
	@echo "Submitting banking-service Cloud Build job..."
	gcloud builds submit --config banking-service/cloudbuild-publish-deploy.yaml --substitutions=_TRIGGER_DEPLOY=false
	@echo "Submitting banking-ui Cloud Build job..."
	gcloud builds submit --config banking-ui/cloudbuild-publish-deploy.yaml --substitutions=_TRIGGER_DEPLOY=false
	@echo "Submitting data-generator Cloud Build job..."
	gcloud builds submit --config data-generator/cloudbuild-publish-deploy.yaml --substitutions=_TRIGGER_DEPLOY=false
	@echo "Submitting credit-support-agent Cloud Build job..."
	gcloud builds submit --config adk-agent/credit-support-agent/cloudbuild-deploy.yaml --substitutions=_TRIGGER_DEPLOY=false

.PHONY: zip-mortgage-agent
zip-mortgage-agent: ## Package the GECX Nova_Horizon_Bot_v2 bundle into a ready-to-upload zip archive
	@echo "Packaging Mortgage Preapproval agent bundle..."
	cd gecx/Nova_Horizon_Bot_v2 && zip -r ../../Nova_Horizon_Bot_v2.zip .
	@echo "Success: Created Nova_Horizon_Bot_v2.zip!"

.PHONY: zip-credit-agent
zip-credit-agent: ## Package the GECX Credit_Support_Voice_Agent bundle into a ready-to-upload zip archive
	@echo "Packaging Credit Support Voice Agent bundle..."
	cd gecx/Credit_Support_Voice_Agent && zip -r ../../Credit_Support_Voice_Agent.zip .
	@echo "Success: Created Credit_Support_Voice_Agent.zip!"

.PHONY: upload-mortgage-agent
upload-mortgage-agent: ## Execute the REST API script to package and import the Mortgage Preapproval agent directly into CES
	@echo "Uploading Mortgage Preapproval Agent to GECX..."
	cd scripts/cxas && PROJECT_ID=$(PROJECT_ID) AGENT_FOLDER=Nova_Horizon_Bot_v2 bash deploy_mortgage_agent.sh

.PHONY: upload-credit-agent
upload-credit-agent: ## Execute the REST API script to package and import the Credit Support Voice Agent directly into CES
	@echo "Uploading Credit Support Voice Agent to GECX..."
	cd scripts/cxas && PROJECT_ID=$(PROJECT_ID) AGENT_FOLDER=Credit_Support_Voice_Agent bash deploy_voice_agent.sh

.PHONY: create-gecx
create-gecx: upload-mortgage-agent upload-credit-agent ## Automate full CES agent provisioning for both Mortgage and Credit agents

.PHONY: update-gecx
update-gecx: ## Execute the overwrite CES agent script to package and overwrite an existing agent in Customer Experience Studio (CES)
ifndef APP_ID
	$(error APP_ID is not defined. Run as: make update-gecx APP_ID=<your-app-id>)
endif
	@echo "Executing overwrite CES agent script for project $(PROJECT_ID) and App ID $(APP_ID)..."
	cd scripts/cxas && PROJECT_ID=$(PROJECT_ID) APP_ID=$(APP_ID) bash overwrite_cxas_agent.sh

.PHONY: patch-convo-profile
patch-convo-profile: ## Patch Dialogflow conversational profile to point to a new agent deployment (usage: make patch-convo-profile CONVERSATIONAL_PROFILE_ID=<profile-id> DEPLOYMENT_ID=<deployment-id>)
ifndef CONVERSATIONAL_PROFILE_ID
	$(error CONVERSATIONAL_PROFILE_ID is not defined. Run as: make patch-convo-profile CONVERSATIONAL_PROFILE_ID=<profile-id> DEPLOYMENT_ID=<deployment-id>)
endif
ifndef DEPLOYMENT_ID
	$(error DEPLOYMENT_ID is not defined. Run as: make patch-convo-profile CONVERSATIONAL_PROFILE_ID=<profile-id> DEPLOYMENT_ID=<deployment-id>)
endif
	@echo "Patching conversational profile $(CONVERSATIONAL_PROFILE_ID) with deployment $(DEPLOYMENT_ID)..."
	cd scripts/cxas && bash patch_conversational_profile.sh -p $(PROJECT_ID) -c $(CONVERSATIONAL_PROFILE_ID) -d $(DEPLOYMENT_ID)

.PHONY: tf-apply
tf-apply: ## Apply all Terraform stages (infrastructure, services, audiences)
	@echo "Running full Terraform deployment (all stages)..."
	cd deployment/terraform && \
		terraform apply -var-file="$(TF_VARS)"

.PHONY: tf-apply-auto-approve
tf-apply-auto-approve: ## Apply all Terraform stages with auto-approve
	@echo "Running full Terraform deployment (all stages, auto-approve)..."
	cd deployment/terraform && \
		terraform apply -auto-approve -var-file="$(TF_VARS)"

.PHONY: tf-apply-initial
tf-apply-initial: ## Argolis Stage 1: Deploy Infrastructure & Cloud Build Triggers (Cloud Run disabled)
	@echo "Applying Argolis Stage 1 (Infrastructure & Triggers)..."
	cd deployment/terraform && \
		terraform apply -auto-approve \
			-var-file="$(TF_VARS)" \
			-var="deploy_cloud_build_triggers=true" \
			-var="deploy_cloud_run_services=false" \
			-var="set_cloud_run_audiences=false" && \
		REGION=$$(terraform output -raw region) && \
		$(MAKE) -C ../.. run-triggers REGION=$$REGION BRANCH=main && \
		echo "Applying Argolis Stage 2 (Deploy Cloud Run services and load balancer for IAP enabled authentication)..." && \
		terraform apply -auto-approve \
			-var-file="$(TF_VARS)" \
			-var="deploy_cloud_build_triggers=true" \
			-var="deploy_cloud_run_services=true" \
			-var="set_cloud_run_audiences=false" && \
		echo "Applying Argolis Stage 3 (Enable Cloud Run audience for IAP enabled authentication on banking service)..." && \
		terraform apply -auto-approve \
			-var-file="$(TF_VARS)" \
			-var="deploy_cloud_build_triggers=true" \
			-var="deploy_cloud_run_services=true" \
			-var="set_cloud_run_audiences=true"

.PHONY: run-triggers
run-triggers: ## Run Cloud Build triggers for a specific branch (usage: make run-triggers BRANCH=feature/foo)
	@if [ -z "$(BRANCH)" ]; then echo "Error: BRANCH is required. Usage: make run-triggers BRANCH=feature/foo"; exit 1; fi
	@echo "Running Cloud Build triggers for branch $(BRANCH)..."
	BUILD_ID=$$(gcloud builds triggers run banking-service-deployment \
		--region=$(REGION) \
		--branch=$(BRANCH) \
		--substitutions=_TRIGGER_DEPLOY=false \
		--format="value(metadata.build.id)") && \
	gcloud builds log $$BUILD_ID --region=$(REGION) --stream

	# Create banking UI artifact
	BUILD_ID=$$(gcloud builds triggers run banking-ui-deployment \
		--region=$(REGION) \
		--branch=$(BRANCH) \
		--substitutions=_TRIGGER_DEPLOY=false \
		--format="value(metadata.build.id)") && \
	gcloud builds log $$BUILD_ID --region=$(REGION) --stream

	# Create credit support agent artifact
	BUILD_ID=$$(gcloud builds triggers run credit-support-agent-deployment \
		--region=$(REGION) \
		--branch=$(BRANCH) \
		--substitutions=_TRIGGER_DEPLOY=false \
		--format="value(metadata.build.id)") && \
	gcloud builds log $$BUILD_ID --region=$(REGION) --stream

	# Create data-generator artifact
	BUILD_ID=$$(gcloud builds triggers run data-generator-deployment \
		--region=$(REGION) \
		--branch=$(BRANCH) \
		--substitutions=_TRIGGER_DEPLOY=false \
		--format="value(metadata.build.id)") && \
	gcloud builds log $$BUILD_ID --region=$(REGION) --stream

	# Create lakehouse view reconcile artifact
	BUILD_ID=$$(gcloud builds triggers run lakehouse-view-reconcile-image \
		--region=$(REGION) \
		--branch=$(BRANCH) \
		--format="value(metadata.build.id)") && \
	gcloud builds log $$BUILD_ID --region=$(REGION) --stream

.PHONY: trigger-site-crawl
trigger-site-crawl:
	@if [ -z "$(BRANCH)" ]; then echo "Error: BRANCH is required. Usage: make run-triggers BRANCH=feature/foo"; exit 1; fi
	@echo "Running Cloud Build trigger for branch $(BRANCH)..."
	BUILD_ID=$$(gcloud builds triggers run banking-ui-crawl \
		--region=$(REGION) \
		--branch=$(BRANCH) \
		--format="value(metadata.build.id)") && \
	gcloud builds log $$BUILD_ID --region=$(REGION) --stream

.PHONY: run-crawl
run-crawl: ## Manually trigger the Playwright web crawler using dynamic CLI substitutions
	@echo "Submitting manual Playwright web crawler job for project $(PROJECT_ID) (domain=$(CUSTOM_DOMAIN))..."
	gcloud builds submit --config scripts/crawl_and_upload/cloudbuild-crawl.yaml \
		--project=$(PROJECT_ID) \
		--service-account="projects/$(PROJECT_ID)/serviceAccounts/cloudbuild-crawler-sa@$(PROJECT_ID).iam.gserviceaccount.com" \
		--substitutions=\
_GCS_BUCKET_NAME=$(PROJECT_ID)-site-crawled-content,\
_USE_GCP_AUTH=true,\
_GCP_AUTH_AUDIENCE=https://banking-ui-$(PROJECT_NUMBER).$(REGION).run.app,\
_SITEMAP_URL=https://banking-ui-$(PROJECT_NUMBER).$(REGION).run.app/sitemap.xml,\
_SITE_BASE_URL=https://$(CUSTOM_DOMAIN),\
_DATA_STORE_ID=$(DATA_STORE_ID)
.PHONY: clean
clean: ## Clean up cached artifacts, dist folders, local dependency directories, and generated zip archives
	@echo "Cleaning cached files, local dependency directories, and top-level archives..."
	rm -rf banking-service/.venv banking-service/__pycache__ banking-service/.pytest_cache
	rm -rf banking-ui/node_modules banking-ui/dist
	rm -f Nova_Horizon_Bot_v2.zip
	@echo "Clean complete."

.PHONY: docker-run-banking-ui
docker-run-banking-ui: ## Run the banking-ui container locally
	@echo "Running banking-ui container locally..."
	cd banking-ui && $(DOCKER) build -t banking-ui-test .
	@FIREBASE_API_KEY=$$(grep apiKey banking-ui/public/fbConfig.js 2>/dev/null | cut -d'"' -f2); \
	FIREBASE_AUTH_DOMAIN=$$(grep authDomain banking-ui/public/fbConfig.js 2>/dev/null | cut -d'"' -f2); \
	FIREBASE_STORAGE_BUCKET=$$(grep storageBucket banking-ui/public/fbConfig.js 2>/dev/null | cut -d'"' -f2); \
	FIREBASE_MEASUREMENT_ID=$$(grep measurementId banking-ui/public/fbConfig.js 2>/dev/null | cut -d'"' -f2); \
	FIREBASE_APP_ID=$$(grep appId banking-ui/public/fbConfig.js 2>/dev/null | cut -d'"' -f2); \
	BANKING_API_URL=$$(grep BANKING_API_URL banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	CCAI_COMPANY_ID=$$(grep CCAI_COMPANY_ID banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	CCAI_HOST=$$(grep CCAI_HOST banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	CX_AGENT_STUDIO_DEPLOYMENT_NAME=$$(grep CX_AGENT_STUDIO_DEPLOYMENT_NAME banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	CX_AGENT_STUDIO_UPLOAD_TOOL_NAME=$$(grep CX_AGENT_STUDIO_UPLOAD_TOOL_NAME banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME=$$(grep CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME=$$(grep CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	LIVEKIT_URL=$$(grep LIVEKIT_URL banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	SHOW_INFO_MODALS=$$(grep SHOW_INFO_MODALS banking-ui/public/config.js 2>/dev/null | cut -d'"' -f2); \
	$(DOCKER) run -ti \
	-e GOOGLE_CLOUD_PROJECT=$(PROJECT_ID) \
	-e BASE_URL="http://localhost:5174" \
	-e FIREBASE_PROJECT_ID=$(PROJECT_ID) \
	-e FIREBASE_API_KEY="$$FIREBASE_API_KEY" \
	-e FIREBASE_AUTH_DOMAIN="$$FIREBASE_AUTH_DOMAIN" \
	-e FIREBASE_STORAGE_BUCKET="$$FIREBASE_STORAGE_BUCKET" \
	-e FIREBASE_MESSAGING_SENDER_ID="$(PROJECT_NUMBER)" \
	-e FIREBASE_APP_ID="$$FIREBASE_APP_ID" \
	-e FIREBASE_MEASUREMENT_ID="$$FIREBASE_MEASUREMENT_ID" \
	-e VITE_BANKING_API_URL="$$BANKING_API_URL" \
	-e VITE_CCAI_COMPANY_ID="$$CCAI_COMPANY_ID" \
	-e VITE_CCAI_HOST="$$CCAI_HOST" \
	-e VITE_CX_AGENT_STUDIO_DEPLOYMENT_NAME="$$CX_AGENT_STUDIO_DEPLOYMENT_NAME" \
	-e VITE_CX_AGENT_STUDIO_UPLOAD_TOOL_NAME="$$CX_AGENT_STUDIO_UPLOAD_TOOL_NAME" \
	-e VITE_CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME="$$CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME" \
	-e VITE_CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME="$$CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME" \
	-e VITE_LIVEKIT_URL="$$LIVEKIT_URL" \
	-e VITE_SHOW_INFO_MODALS="$$SHOW_INFO_MODALS" \
	-p 5174:8080 \
	banking-ui-test

.PHONY: docker-run-banking-service
docker-run-banking-service: ## Run the banking-service container locally
	@echo "Running banking-service container locally..."
	cd banking-service && $(DOCKER) build -t banking-service-test .
	$(DOCKER) run -ti \
	-v "$(HOME)/.config/gcloud/application_default_credentials.json":/gcp/creds.json \
	-e GOOGLE_APPLICATION_CREDENTIALS=/gcp/creds.json \
	-e GOOGLE_CLOUD_PROJECT=$(PROJECT_ID) \
	-e DISCOVERY_ENGINE_ID="banking-site_1778875783412" \
	-p 8080:8080 \
	banking-service-test

.PHONY: docker-run-iap-login-ui
docker-run-iap-login-ui: ## Run the iap-login-ui container locally
	@echo "Running iap-login-ui container locally..."
	cd iap-login-ui && $(DOCKER) build -t iap-login-ui-test .
	@FIREBASE_API_KEY=$$(grep apiKey iap-login-ui/config.js 2>/dev/null | cut -d'"' -f2); \
	FIREBASE_AUTH_DOMAIN=$$(grep authDomain iap-login-ui/config.js 2>/dev/null | cut -d'"' -f2); \
	$(DOCKER) run -ti \
	-v "$(HOME)/.config/gcloud/application_default_credentials.json":/gcp/creds.json \
	-e GOOGLE_APPLICATION_CREDENTIALS=/gcp/creds.json \
	-e GOOGLE_CLOUD_PROJECT=$(PROJECT_ID) \
	-e FIREBASE_PROJECT_ID=$(PROJECT_ID) \
	-e FIREBASE_API_KEY="$$FIREBASE_API_KEY" \
	-e FIREBASE_AUTH_DOMAIN="$$FIREBASE_AUTH_DOMAIN" \
	-e FIREBASE_PROJECT_NUMBER="$(PROJECT_NUMBER)" \
	-e BASE_PATH="/" \
	-p 8080:8080 \
	iap-login-ui-test
