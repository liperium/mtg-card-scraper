#!/usr/bin/env bash
set -e

ssh 192.168.0.15 << 'EOF'
  cd ~/nix-conf
  nix flake update mtg-card-scraper
  nh os switch ~/nix-conf/ --accept-flake-config
EOF