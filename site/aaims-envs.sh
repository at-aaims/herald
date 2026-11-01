#!/bin/bash
# This script is used to fetch data access credentials using OLCF accounts
# associated to a particular staff project. The script will prompt the user
# with the username and passcode to be able to fetch the credentials and setup
# the environment variables for the user to access the data.
#
# We currently rely on our OpenShift deployment to be able to fetch the
# credentials from the secrets stored in the staff project.

echo "Credentials Setup / Teardown"
ROOT_DIR=$(cd $(dirname $(dirname $0)) && pwd)
SITE_PROFILE=aaims
APP_NAME=$(basename ${ROOT_DIR})
echo ${ROOT_DIR}
if [ $# -lt 1 ]; then
	echo "Usage: $(basename $0) <setup|teardown>"
	exit 1
fi
CMD=$1

#
# Environment variables specific to the ORNL NCCS AAIMS group
#
# Passed to the .env file for the application
#

# A posix based local path used for local storage
SCRATCH_BASE=$(pwd)/.scratch
SHARED_BASE=$(pwd)/.shared
DEFAULT_PREFIX="s3a://"

# Object storage location (posix in this case)
DATA_BASE=${DEFAULT_PREFIX}stream
DATA_PRIV_BASE=${DEFAULT_PREFIX}stream-sens

# Minio server information
AWS_ENDPOINT_URL=https://<your-minio-host>
AWS_ACCESS_KEY_ID=""
AWS_SECRET_KEY_ACCESS=""

KUBECONFIG="~/.kube/config"
KUBERNETES_SERVICE_HOST=https://<your-k8s-api-host>
KUBERNETES_SERVICE_PORT=443
KUBERNETES_NAMESPACE=<your-namespace>-obs
KUBERNETES_APP_NAMESPACE=<your-namespace>-app
KUBERNETES_BATCH_NAMESPACE=<your-namespace>-batch

# Compilation
DOTENV_PAYLOAD="
# Site profile
SITE_PROFILE=${SITE_PROFILE}

# Application information
APP_NAME=${APP_NAME}
# BASE_PATH=""

# Model configuration
LARGE_MODEL__TYPE="openai"
LARGE_MODEL__NAME="gpt-4o"
LARGE_MODEL__URL="https://<your-resource>.openai.azure.com/openai/deployments/gpt-4o?api-version=2025-01-01-preview"
LARGE_MODEL__KEY=Add your API key

SMALL_MODEL__TYPE="local"
SMALL_MODEL__NAME="meta-llama/Meta-Llama-3.1-8B-Instruct"

SQL_MODEL__TYPE="local"
SQL_MODEL__NAME="defog/llama-3-sqlcoder-8b"

# Obsidian data access
SCRATCH_BASE=${SCRATCH_BASE}
SHARED_BASE=${SHARED_BASE}
DATA_BASE=${DATA_BASE}
DATA_PRIV_BASE=${DATA_PRIV_BASE}

# Nvidia GPU selection
CUDA_VISIBLE_DEVICES=0

# Kubernetes
KUBECONFIG=${KUBECONFIG}
KUBERNETES_SERVICE_HOST=${KUBERNETES_SERVICE_HOST}
KUBERNETES_SERVICE_PORT=${KUBERNETES_SERVICE_PORT}
KUBERNETES_NAMESPACE=${KUBERNETES_NAMESPACE}
KUBERNETES_APP_NAMESPACE=${KUBERNETES_APP_NAMESPACE}
KUBERNETES_BATCH_NAMESPACE=${KUBERNETES_BATCH_NAMESPACE}

"

# Variables private to the script

# Image registry information
IMAGE_REGISTRY_URL=<your-registry-host>
IMAGE_REGISTRY=${WORK_NAMESPACE}
IMAGE_NAME=${APP_NAME}
IMAGE_TAG=dev-${USER}
IMAGE_PATH=${IMAGE_REGISTRY_URL}/${IMAGE_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}


#
# Checks for the prerequisites
#

OC=oc
MC=mc

# Check for required commands
if ! command -v oc &>/dev/null; then
	echo "Error: 'oc' command not found"
	exit 1
fi
if ! command -v mc &>/dev/null; then
	echo "Error: 'mc' command not found"
	exit 1
fi
if ! command -v base64 &>/dev/null; then
	echo "Error: 'base64' command not found"
	exit 1
fi

#
# Main script
#

case ${CMD} in
setup)
	USTYPE=$2
	SECRET=miniogw-access
	set -e
	echo "authenticating nccs user"
	read -p 'nccs account: ' USERID
	read -sp 'passcode: ' PASSCODE
	echo ""
	oc login ${API_SERVER} -u ${USERID} -p ${PASSCODE} 2>&1 >/dev/null

	#
	# Staff login
	#
	
	# Credentials are from a predetermined kubernetes secret only accessible through
	# OpenShift Oauth2 authentication. We fetch the credentials and setup the environment
	ACCESS_KEY_ID=`${OC} -n ${KUBERNETES_NAMESPACE} get secret miniogw-access -o jsonpath='{.data.access_key_id}'|base64 -d`
	SECRET_ACCESS_KEY=`${OC} -n ${KUBERNETES_NAMESPACE} get secret miniogw-access -o jsonpath='{.data.secret_access_key}'|base64 -d`

	# Setup minio client credentials
	echo "- minio client 'mc' alias 'orb'"
	mkdir -p ~/.mc && chmod 700 ~/.mc \
		&& echo "{\"url\": \"${MINIO_SERVER}\", \"accessKey\": \"${ACCESS_KEY_ID}\", \"secretKey\": \"${SECRET_ACCESS_KEY}\", \"api\": \"s3v4\", \"path\": \"auto\" }" > ~/.mc/orb.json \
		&& mc alias import orb ~/.mc/orb.json \
		&& rm ~/.mc/orb.json

	# After fetching secrets, switch to the batch namespace instead of the obs one
	oc project ${KUBERNETES_BATCH_NAMESPACE} 2>&1 >/dev/null

	# Setup environment variables via dotenv
	touch ${ROOT_DIR}/.env
	chmod 600 ${ROOT_DIR}/.env
	echo "${DOTENV_PAYLOAD}" > ${ROOT_DIR}/.env

	# Point AWS credentials to our minio server
	echo "# AWS credentials" >> ${ROOT_DIR}/.env
	echo "AWS_ENDPOINT_URL=${MINIO_SERVER}" >> ${ROOT_DIR}/.env
	echo "AWS_ACCESS_KEY_ID=${ACCESS_KEY_ID}" >> ${ROOT_DIR}/.env
	echo "AWS_SECRET_ACCESS_KEY=${SECRET_ACCESS_KEY}" >> ${ROOT_DIR}/.env
	echo "" >> ${ROOT_DIR}/.env

	echo "@ credential setup success"
	exit 0
	;;
teardown)
	echo "@ removing local credentials"
	# Remove environment variables
	rm ${ROOT_DIR}/.env

	# Remove minio client credentials
	echo "@ Removing minio aliases orb"
	mc alias rm orb

	echo "@ logout success"
	;;
esac
exit 0
