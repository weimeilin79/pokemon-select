# Pokémon Recommender : A Cloud Assist Demo

## Overview

Welcome to the Pokémon Recommender! This project is a demonstration of how Google Cloud's AI and infrastructure services can be combined to build a powerful, real-world application.  Imagine you're a new Pokémon trainer, embarking on your journey. Choosing your first Pokemon is a critical decision! This application acts as your personal assistant, leveraging a Retrieval-Augmented Generation (RAG) system to help you make the perfect choice. By understanding your preferences and the unique characteristics of each starter Pokemon, the assistant provides tailored recommendations. This demo showcases the power of Cloud Assist, highlighting how it can guide developers in building complex, cloud-native applications.

![The app](the_app.png)


## Cloud Architecture

![GCP Architecture](cloud_architecture.png)

This application is built on a robust and scalable cloud architecture, leveraging the following Google Cloud services:

*   **Kubernetes Engine (GKE):** The core of the application runs on GKE, providing a containerized and orchestrated environment for the web application. This ensures high availability, scalability, and efficient resource utilization.
*   **Cloud SQL for PostgreSQL:**  We use Cloud SQL as our managed relational database service. It stores the Pokemon data, including their names, descriptions, and other relevant information.
*   **Vector Database (PostgreSQL Extension):**  To enable semantic search and similarity matching, we utilize the `vector` extension within PostgreSQL. This allows us to store and query Pokemon embeddings, which are numerical representations of their descriptions.
*   **Vertex AI:** Vertex AI's text embedding model is used to generate the vector embeddings for the Pokemon descriptions. These embeddings are then stored in the vector database, enabling the RAG system to find the most relevant Pokemon based on user input.
* **Dataflow:** Dataflow is used to load the pokemon data into the database.
* **Artifact Registry:** Artifact Registry is used to store the container images for the application and dataflow.
* **Cloud Storage:** Cloud Storage is used to store the pokemon description files and images.

## Installation

Don't forget to set your project ID
```
export PROJECT_ID="<YOUR_PROJECT_ID>" 
```

```
gcloud services enable \
    compute.googleapis.com \
    container.googleapis.com \
    sqladmin.googleapis.com \
    storage.googleapis.com \
    dataflow.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    logging.googleapis.com \
    monitoring.googleapis.com \
    cloudresourcemanager.googleapis.com \
    iam.googleapis.com \
    servicenetworking.googleapis.com \
    aiplatform.googleapis.com


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


#cloud Resource Manager


# Create VPC Network
gcloud compute networks create $NETWORK_NAME --subnet-mode=custom

# Create Subnet
gcloud compute networks subnets create $SUBNET_NAME \
    --network=$NETWORK_NAME \
    --range=10.0.1.0/24 \
    --region=$REGION \
    --enable-private-ip-google-access

gcloud compute networks subnets update $SUBNET_NAME \
    --region=us-central1 \
    --enable-private-ip-google-access

gcloud compute firewall-rules create dataflow-internal-ports \
    --network=pokemon-vpc \
    --action=ALLOW \
    --direction=INGRESS \
    --rules=tcp:12345-12346 \
    --source-ranges=10.0.0.0/8 \
    --description="Allow internal Dataflow communication on ports 12345-12346"


gcloud compute firewall-rules create allow-http-https-ingress \
    --network=$NETWORK_NAME \
    --direction=INGRESS \
    --priority=1000 \
    --action=ALLOW \
    --rules=tcp:80,tcp:443 \
    --source-ranges=0.0.0.0/0,130.211.0.0/22,35.191.0.0/16 \
    --description="Allow incoming HTTP/S traffic from internet and LB health checks"


# Configure Private Service Access for Cloud SQL
gcloud compute addresses create google-managed-services-$NETWORK_NAME \
    --global \
    --purpose=VPC_PEERING \
    --prefix-length=16 \
    --network=$NETWORK_NAME
gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --ranges=google-managed-services-$NETWORK_NAME \
    --network=$NETWORK_NAME \
    --project=$PROJECT_ID
    
# Create database instance
gcloud sql instances create $SQL_INSTANCE_NAME \
    --database-version=POSTGRES_16 \
    --tier=db-perf-optimized-N-2 \
    --region=$REGION \
    --network=$NETWORK_NAME \
    --no-assign-ip

# Set root password (we'll use Root)
gcloud sql users set-password postgres --instance=$SQL_INSTANCE_NAME --prompt-for-password

# Create the database
gcloud sql databases create $DB_NAME --instance=$SQL_INSTANCE_NAME


#gcloud sql connect $SQL_INSTANCE_NAME --user=postgres

######################################################
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE pokemon (
    name VARCHAR(255) PRIMARY KEY,
    description TEXT,
    embedding vector(768) -- Correct dimension for text-embedding-005
);


CREATE INDEX pokemon_embedding_idx ON pokemon
USING hnsw (embedding vector_l2_ops)
WITH (m = 16, ef_construction = 256);
######################################################



# Service Account for GKE Pods
gcloud iam service-accounts create $GKE_SA_NAME \
    --display-name="Pokemon App GKE SA"

# Service Account for Dataflow
gcloud iam service-accounts create $DATAFLOW_SA_NAME \
    --display-name="Pokemon Dataflow SA"

# Grant Dataflow SA necessary roles (e.g., Dataflow Worker, Cloud SQL Client)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DATAFLOW_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/dataflow.worker"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DATAFLOW_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DATAFLOW_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/monitoring.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DATAFLOW_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/logging.logWriter"

    
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/monitoring.admin"


# INTENTIONALLY Grant overly permissive role for IAM recommendation demo
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DATAFLOW_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/editor" # Overly broad! Cloud Assist should flag this.



# Create dummy description files locally
echo "A cute electric mouse Pokemon, known for its speed and electric shocks." > pikachu.txt
echo "A small fire lizard Pokemon. The flame on its tail indicates its life force." > charmander.txt
echo "A tiny turtle Pokemon that cleverly uses its shell for protection and attacks." > squirtle.txt
echo "A seed Pokemon with a bulb on its back that grows as it does." > bulbasaur.txt

gsutil mb -l $REGION gs://$BUCKET_NAME

# Define the GCS input data folder
export GCS_DATA_FOLDER="gs://${BUCKET_NAME}/pokemon-descriptions/"

# Upload the files to GCS
gsutil cp *.txt $GCS_DATA_FOLDER
rm *.txt # Clean up local files


cd ~/data_prep
python -m venv env
source env/bin/activate
pip install -r df_requirements.txt


export IP_TEMP=$(gcloud sql instances describe $SQL_INSTANCE_NAME --format="value(ipAddresses[0].ipAddress)" | grep -oE "^([0-9]{1,3}\.){2}" | sed 's/\.$//' )


gcloud compute firewall-rules create allow-dataflow-egress-google \
    --project=$PROJECT_ID \
    --direction=EGRESS \
    --priority=900 \
    --network=pokemon-vpc \
    --action=ALLOW \
    --rules=tcp:80,tcp:443 \
    --destination-ranges=0.0.0.0/0 \
    --target-tags=dataflow-worker \
    --description="Allow Dataflow workers to reach Google APIs and services"


gcloud compute firewall-rules create allow-dataflow-egress-cloudsql \
    --project=$PROJECT_ID \
    --direction=EGRESS \
    --priority=900 \
    --network=pokemon-vpc \
    --action=ALLOW \
    --rules=tcp:5432 \
    --destination-ranges=$IP_TEMP.0.0/16 \
    --target-tags=dataflow-worker \
    --description="Allow Dataflow workers to reach Cloud SQL"

gcloud compute firewall-rules create allow-app-egress-cloudsql \
    --project=$PROJECT_ID \
    --direction=EGRESS \
    --priority=900 \
    --network=pokemon-vpc \
    --action=ALLOW \
    --rules=tcp:3307 \
    --destination-ranges=$IP_TEMP.0.0/16 \
    --description="Allow application to reach Cloud SQL via cloud-sql-proxy"

gcloud compute firewall-rules create allow-app-ingress-cloudsql \
    --project=$PROJECT_ID \
    --direction=INGRESS \
    --priority=900 \
    --network=pokemon-vpc \
    --action=ALLOW \
    --rules=tcp:3307 \
    --source-ranges=0.0.0.0/0  \
    --description="Allow inbound connections on 3307 to application (ONLY if needed)"

# Get the Private IP address (needed for the app)
export DB_HOST=$(gcloud sql instances describe $SQL_INSTANCE_NAME --format="value(ipAddresses[0].ipAddress)")
echo "Database Private IP: $DB_HOST"

export GCS_DATA_FOLDER="gs://${BUCKET_NAME}/pokemon-descriptions/"
export DF_STAGING_LOCATION="gs://${BUCKET_NAME}/dataflow/staging"
export DF_TEMP_LOCATION="gs://${BUCKET_NAME}/dataflow/temp"
export DF_INPUT_PATTERN="${GCS_DATA_FOLDER}*.txt"


gcloud auth configure-docker ${REGION}-docker.pkg.dev
# Build the image using Cloud Build
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}/dataflow/txt-embedding-lib:latest .


export DF_JOB_NAME="pokemon-load-txt-2-embedding-1"
# Run the pipeline (use --input_pattern instead of --input)

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


cd ~/webapp
python -m venv env
source env/bin/activate
pip install -r requirements.txt


export INSTANCE_CONNECTION_NAME=$(gcloud sql instances describe $SQL_INSTANCE_NAME --project=$PROJECT_ID --format='value(connectionName)')
echo "Instance Connection Name: $INSTANCE_CONNECTION_NAME"

#If you want to run it locally
#cloud-sql-proxy --private-ip $INSTANCE_CONNECTION_NAME &

#Artifact Registry:
gcloud artifacts repositories create $AR_REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --description="Pokemon app container images"


# Build the image using Cloud Build
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO_NAME}/pokemon-app:latest .

cd ~/k8s

#GKE 
gcloud container clusters create $CLUSTER_NAME \
    --zone=$ZONE \
    --num-nodes=1 \
    --machine-type=e2-small \
    --network=$NETWORK_NAME \
    --subnetwork=$SUBNET_NAME \
    --service-account="${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --enable-ip-alias \
    --scopes="https://www.googleapis.com/auth/cloud-platform" #Grant almost all access to GKE

#Enabling/Updating Workload Identity for cluster 
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --workload-pool=${PROJECT_ID}.svc.id.goog
  
# Get credentials for kubectl
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE
kubectl create serviceaccount $GKE_SA_NAME -n default

# Variables from before

export GSA_EMAIL="${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export KSA_NAME="pokemon-app-sa" # Kubernetes SA name
export K8S_NAMESPACE="default"     # Kubernetes namespace

echo "Binding KSA $KSA_NAME/$K8S_NAMESPACE to GSA $GSA_EMAIL for Workload Identity..."

gcloud iam service-accounts add-iam-policy-binding $GSA_EMAIL \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${K8S_NAMESPACE}/${KSA_NAME}]"



# Create Kubernetes secret for DB password
kubectl create secret generic cloudsql-db-credentials \
    --from-literal=username=$DB_USER \
    --from-literal=password=$DB_PASSWORD

sed -i "s|\${REGION}|${REGION}|g" deployment.yaml
sed -i "s|\${PROJECT_ID}|${PROJECT_ID}|g" deployment.yaml
sed -i "s|\${AR_REPO_NAME}|${AR_REPO_NAME}|g" deployment.yaml
sed -i "s|\${GKE_SA_NAME}|${GKE_SA_NAME}|g" deployment.yaml 
sed -i "s|\${BUCKET_NAME}|${BUCKET_NAME}|g" deployment.yaml
sed -i "s|\${DB_USER}|${DB_USER}|g" deployment.yaml
sed -i "s|\${DB_NAME}|${DB_NAME}|g" deployment.yaml
sed -i "s|\${INSTANCE_CONNECTION_NAME}|${INSTANCE_CONNECTION_NAME}|g" deployment.yaml


export GKE_SA_NAME="pokemon-app-sa"
export GSA_EMAIL="${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export KSA_NAME="pokemon-app-sa"
export K8S_NAMESPACE="default"

# Echo them to be sure
echo "PROJECT_ID: $PROJECT_ID"
echo "GSA_EMAIL: $GSA_EMAIL"
echo "KSA_NAME: $KSA_NAME"
echo "K8S_NAMESPACE: $K8S_NAMESPACE"
echo "MEMBER_STRING: serviceAccount:${PROJECT_ID}.svc.id.goog[${K8S_NAMESPACE}/${KSA_NAME}]"

#IAM Binding: Run the add-iam-policy-binding
gcloud iam service-accounts add-iam-policy-binding $GSA_EMAIL \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${K8S_NAMESPACE}/${KSA_NAME}]"


export NODE_SA_EMAIL=$(gcloud container node-pools describe $NODE_POOL_NAME   --cluster=$CLUSTER_NAME   --region=$ZONE   --project=$PROJECT_ID   --format='value(config.serviceAccount)')
echo "Granting Artifact Registry Reader to Node SA $NODE_SA_EMAIL on repo $AR_REPO_NAME..."

gcloud artifacts repositories add-iam-policy-binding $AR_REPO_NAME \
  --location=$REGION \
  --project=$PROJECT_ID \
  --member="serviceAccount:$NODE_SA_EMAIL" \
  --role="roles/artifactregistry.reader"

kubectl apply -f deployment.yaml 
kubectl apply -f service.yaml 


# Grant permission needed to create signed URLs (token creator on the SA itself)
gcloud iam service-accounts add-iam-policy-binding \
  ${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com \
  --project=$PROJECT_ID \
  --member="serviceAccount:${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"




#FIX ONE - don't forget to set the project id
./rerun.sh

#FIX TWO

# Grant permission to read objects from the bucket
gsutil iam ch \
  serviceAccount:${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com:objectViewer \
  gs://${BUCKET_NAME}


#REVERSE FIX
# Remove permission to read objects from the bucket
gsutil iam ch -d \
  serviceAccount:${GKE_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com:objectViewer \
  gs://${BUCKET_NAME}

```