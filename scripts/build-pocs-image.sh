#!/bin/bash
# Build and push the huntsmanarray/panoptes-pocs:commissioning image
# Run this before building huntsmanarray/huntsman-pocs:commissioning images
set -eu

cd ${POCS}
docker buildx build \
  -f docker/Dockerfile \
  --build-arg "image_url=gcr.io/panoptes-exp/panoptes-utils:develop" \
  --platform linux/amd64,linux/arm64 \
  --tag huntsmanarray/panoptes-pocs:commissioning \
  --output "type=image,push=true" .
