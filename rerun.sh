#!/bin/bash

export PROJECT_ID="pokedemo-test" 
export REGION="us-central1"             
export ZONE="us-central1-c"             
export CLUSTER_NAME="pokemon-cluster"
export SQL_INSTANCE_NAME="pokemon-db-instance"
export DB_NAME="pokemon_db"
export DB_USER="postgres"
export DB_PASSWORD="1234qwer" 
export BUCKET_NAME="pokemon-images-${PROJECT_ID}" 
export AR_REPO_NAME="pokemon-app-repo"
export GKE_SA_NAME="pokemon-app-sa" 
export DATAFLOW_SA_NAME="pokemon-dataflow-sa" 
export NETWORK_NAME="pokemon-vpc"
export SUBNET_NAME="pokemon-subnet"
export GOOGLE_GENAI_USE_VERTEXAI=True
export DB_HOST_PROXY="127.0.0.1"
export NODE_POOL_NAME="default-pool" 
gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
gcloud config set compute/zone $ZONE


# Get the Private IP address (needed for the app)
export DB_HOST=$(gcloud sql instances describe $SQL_INSTANCE_NAME --format="value(ipAddresses[0].ipAddress)")
echo "Database Private IP: $DB_HOST"

export GCS_DATA_FOLDER="gs://${BUCKET_NAME}/pokemon-descriptions/"
export DF_STAGING_LOCATION="gs://${BUCKET_NAME}/dataflow/staging"
export DF_TEMP_LOCATION="gs://${BUCKET_NAME}/dataflow/temp"
export DF_INPUT_PATTERN="${GCS_DATA_FOLDER}*.txt"

export DF_JOB_NAME="pokemon-load-txt-2-embedding-1"


source env/bin/activate
python dataflow_pipeline.py \
  --runner=DataflowRunner \
  --project=$PROJECT_ID \
  --region=$REGION \
  --job_name=$DF_JOB_NAME \
  --temp_location=$DF_TEMP_LOCATION \
  --input_pattern=$DF_INPUT_PATTERN \
  --service_account_email="${DATAFLOW_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --network=$NETWORK_NAME \
  --subnetwork="regions/${REGION}/subnetworks/${SUBNET_NAME}" \
  --no_use_public_ips \
  --input_pattern=$DF_INPUT_PATTERN \
  --db_host=$DB_HOST \
  --db_name=$DB_NAME \
  --db_user=$DB_USER \
  --db_password=$DB_PASSWORD \
  --experiments=use_runner_v2 \
  --sdk_container_image=${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}/dataflow/txt-embedding-lib:latest \
  --sdk_location=container