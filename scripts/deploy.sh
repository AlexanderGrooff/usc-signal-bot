#!/usr/bin/env bash

set -x
set -e

CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || git rev-parse --short HEAD)

docker build -t $HARBOR_REGISTRY_URL/library/usc-signal-bot:$CURRENT_TAG .
docker login -u "$HARBOR_REGISTRY_USERNAME" -p "$HARBOR_REGISTRY_PASSWORD" "$HARBOR_REGISTRY_URL"
docker push "$HARBOR_REGISTRY_URL/library/usc-signal-bot:$CURRENT_TAG"
docker tag $HARBOR_REGISTRY_URL/library/usc-signal-bot:$CURRENT_TAG $HARBOR_REGISTRY_URL/library/usc-signal-bot:latest
docker push "$HARBOR_REGISTRY_URL/library/usc-signal-bot:latest"
