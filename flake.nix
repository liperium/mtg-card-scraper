{
  description = "MTG Card Scraper - FastAPI backend + SvelteKit frontend";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # NixOS module for running as a service
      nixosModule = { config, lib, pkgs, ... }:
        let
          cfg = config.services.mtg-scraper;
          pkg = self.packages.${pkgs.system}.nativeRelease;
        in
        {
          options.services.mtg-scraper = {
            enable = lib.mkEnableOption "MTG Card Scraper web service";

            port = lib.mkOption {
              type = lib.types.port;
              default = 8000;
              description = "Port to listen on";
            };

            address = lib.mkOption {
              type = lib.types.str;
              default = "0.0.0.0";
              description = "Address to bind to";
            };

            openFirewall = lib.mkOption {
              type = lib.types.bool;
              default = false;
              description = "Open firewall for the service port";
            };

            dataDir = lib.mkOption {
              type = lib.types.path;
              default = "/var/lib/mtg-scraper";
              description = "Directory for storing scraped data";
            };
          };

          config = lib.mkIf cfg.enable {
            systemd.services.mtg-scraper = {
              description = "MTG Card Price Scraper API";
              wantedBy = [ "multi-user.target" ];
              after = [ "network.target" ];

              serviceConfig = {
                Type = "simple";
                ExecStart = "${pkg}/bin/mtg-scraper --host ${cfg.address} --port ${toString cfg.port}";
                Restart = "on-failure";
                RestartSec = 5;

                # Run as dedicated user
                DynamicUser = true;
                StateDirectory = "mtg-scraper";
                WorkingDirectory = cfg.dataDir;

                # Chromium needs these; MTG_FRONTEND_DIST tells FastAPI where static files are
                Environment = [
                  "HOME=/var/lib/mtg-scraper"
                  "XDG_CONFIG_HOME=/var/lib/mtg-scraper/.config"
                  "XDG_CACHE_HOME=/var/lib/mtg-scraper/.cache"
                  "MTG_FRONTEND_DIST=${self.packages.${pkgs.system}.frontend}"
                ];

                # Hardening
                NoNewPrivileges = true;
                ProtectSystem = "strict";
                ProtectHome = true;
                PrivateTmp = true;
                ReadWritePaths = [ cfg.dataDir ];
              };
            };

            networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [ cfg.port ];
          };
        };
    in
    flake-utils.lib.eachDefaultSystem
      (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};

          # Copy source files to nix store (filtered)
          src = pkgs.lib.cleanSourceWith {
            src = ./.;
            filter = path: type:
              let
                name = baseNameOf path;
              in
              (pkgs.lib.hasSuffix ".py" name) ||
              (type == "directory" && name == "vendors") ||
              (type == "directory" && name == "cart") ||
              (type == "directory" && name == "api") ||
              (name == "pyproject.toml");
          };

          # Python environment with all dependencies
          pythonEnv = pkgs.python313.withPackages (ps: with ps; [
            fastapi
            uvicorn
            sse-starlette
            pandas
            selenium
            pyperclip
            setuptools
            undetected-chromedriver
          ]);

          # Script to run the API backend (development — uses live source)
          runScript = pkgs.writeShellScriptBin "mtg-scraper" ''
            cd ${./.}
            export PYTHONPATH="${./.}:$PYTHONPATH"
            export CHROME_BIN="${pkgs.chromium}/bin/chromium"
            export CHROMEDRIVER_PATH="${pkgs.chromedriver}/bin/chromedriver"
            ${pythonEnv}/bin/uvicorn api.main:app --host "''${HOST:-127.0.0.1}" --port "''${PORT:-8000}" "$@"
          '';

          # Script to run the API backend (release/service)
          runScriptRelease = pkgs.writeShellScriptBin "mtg-scraper" ''
            export PYTHONPATH="${src}:$PYTHONPATH"
            export CHROME_BIN="${pkgs.chromium}/bin/chromium"
            export CHROMEDRIVER_PATH="${pkgs.chromedriver}/bin/chromedriver"
            ${pythonEnv}/bin/uvicorn api.main:app "$@"
          '';

        in
        {
          packages = {
            # Default: native Python backend (dev)
            default = runScript;

            # Release mode (service-friendly, uses nix store src)
            nativeRelease = runScriptRelease;

            # Frontend static build
            # NOTE: run `npm install` in frontend/ first to generate package-lock.json,
            # then add the npmDepsHash from `prefetch-npm-deps frontend/package-lock.json`
            # frontend = pkgs.buildNpmPackage {
            #   pname = "mtg-scraper-frontend";
            #   version = "0.1.0";
            #   src = ./frontend;
            #   npmDepsHash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";
            #   buildPhase = "npm run build";
            #   installPhase = "cp -r build $out";
            # };
            frontend = pkgs.runCommand "mtg-scraper-frontend-placeholder" {} ''
              mkdir -p $out
              echo "Run npm install && npm run build in frontend/ first" > $out/README
            '';
          };

          # Development shell
          devShells.default = pkgs.mkShell {
            buildInputs = [
              pythonEnv
              pkgs.chromium
              pkgs.chromedriver
              pkgs.nodejs_22
              pkgs.bun
            ];

            shellHook = ''
              export CHROME_BIN=${pkgs.chromium}/bin/chromium
              export CHROMEDRIVER_PATH=${pkgs.chromedriver}/bin/chromedriver
              echo "MTG Card Scraper development environment"
              echo ""
              echo "Backend:  uvicorn api.main:app --reload"
              echo "Frontend: cd frontend && bun install && bun run dev"
            '';
          };

          # Apps for easy running
          apps = {
            default = {
              type = "app";
              program = "${self.packages.${system}.default}/bin/mtg-scraper";
            };

            nativeRelease = {
              type = "app";
              program = "${self.packages.${system}.nativeRelease}/bin/mtg-scraper";
            };
          };
        }
      ) // {
      # Export NixOS module
      nixosModules.default = nixosModule;
      nixosModules.mtg-scraper = nixosModule;
    };
}
