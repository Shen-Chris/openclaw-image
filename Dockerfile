# syntax=docker/dockerfile:1
# Use the official browser image; never copy production state into an image.
# CI resolves every selected release to a verified manifest digest.
ARG BASE_IMAGE=ghcr.io/openclaw/openclaw:2026.11.4-browser@sha256:82848fb1e0f5e0a589fcc08fc700a54f354a98371db9d96bb7f3d5468e894ab0
FROM ${BASE_IMAGE}

USER root

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        vim \
        netcat-openbsd \
        ffmpeg \
        fontconfig \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Inherit the upstream entrypoint, command, healthcheck and browser environment.
USER node
