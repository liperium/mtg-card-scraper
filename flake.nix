{
  description = "MTG Card Scraper - Streamlit app for scraping card prices";

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
              default = 8501;
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
              description = "MTG Card Price Scraper";
              wantedBy = [ "multi-user.target" ];
              after = [ "network.target" ];

              serviceConfig = {
                Type = "simple";
                ExecStart = "${pkg}/bin/mtg-scraper --server.port ${toString cfg.port} --server.address ${cfg.address}";
                Restart = "on-failure";
                RestartSec = 5;

                # Run as dedicated user
                DynamicUser = true;
                StateDirectory = "mtg-scraper";
                WorkingDirectory = cfg.dataDir;

                # Chromium needs these
                Environment = [
                  "HOME=/var/lib/mtg-scraper"
                  "XDG_CONFIG_HOME=/var/lib/mtg-scraper/.config"
                  "XDG_CACHE_HOME=/var/lib/mtg-scraper/.cache"
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
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Copy source files to nix store (filtered)
        src = pkgs.lib.cleanSourceWith {
          src = ./.;
          filter = path: type:
            let
              name = baseNameOf path;
            in
            # Include Python files and necessary assets
            (pkgs.lib.hasSuffix ".py" name) ||
            (type == "directory" && name == "vendors") ||
            (type == "directory" && name == "cart") ||
            (name == "pyproject.toml");
        };

        # Python environment with all dependencies
        pythonEnv = pkgs.python313.withPackages (ps: with ps; [
          streamlit
          pandas
          selenium
          pyperclip
          setuptools
          undetected-chromedriver
        ]);

        # Script to run the app with native Python (development)
        runScript = pkgs.writeShellScriptBin "mtg-scraper" ''
          cd ${./.}
          export PYTHONPATH="${./.}:$PYTHONPATH"
          export PATH="${pkgs.chromium}/bin:${pkgs.chromedriver}/bin:$PATH"
          export CHROME_BIN="${pkgs.chromium}/bin/chromium"
          export CHROMEDRIVER_PATH="${pkgs.chromedriver}/bin/chromedriver"
          ${pythonEnv}/bin/streamlit run app.py "$@"
        '';

        # Script to run the app with native Python (release/service)
        runScriptRelease = pkgs.writeShellScriptBin "mtg-scraper" ''
          export PYTHONPATH="${src}:$PYTHONPATH"
          export PATH="${pkgs.chromium}/bin:${pkgs.chromedriver}/bin:$PATH"
          export CHROME_BIN="${pkgs.chromium}/bin/chromium"
          export CHROMEDRIVER_PATH="${pkgs.chromedriver}/bin/chromedriver"
          ${pythonEnv}/bin/streamlit run ${src}/app.py \
            --server.headless true \
            --server.fileWatcherType none \
            --client.showErrorDetails false \
            --browser.gatherUsageStats false \
            "$@"
        '';

        # Script to run the app with uv
        uvRunScript = pkgs.writeShellScriptBin "mtg-scraper-uv" ''
          cd ${./.}
          ${pkgs.uv}/bin/uv run streamlit run app.py "$@"
        '';

      in
      {
        packages = {
          # Default: Use uv (matches your current setup)
          default = pkgs.writeShellScriptBin "mtg-scraper" ''
            cd ${./.}
            ${pkgs.uv}/bin/uv run streamlit run app.py "$@"
          '';

          # Alternative: Native Python with modules (dev)
          native = runScript;

          # Native Python release mode (service-friendly)
          nativeRelease = runScriptRelease;

          # Explicit uv version
          uv = uvRunScript;
        };


        # Development shell with all tools
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.uv
            pkgs.chromium # For selenium
          ];

          shellHook = ''
            echo "MTG Card Scraper development environment"
            echo "Run 'streamlit run app.py' to start the app"
            echo "Or use 'uv run streamlit run app.py'"

            # Set Chrome/Chromium path for Selenium
            export CHROME_BIN="${pkgs.chromium}/bin/chromium"
          '';
        };

        # Apps for easy running
        apps = {
          default = {
            type = "app";
            program = "${self.packages.${system}.default}/bin/mtg-scraper";
          };

          native = {
            type = "app";
            program = "${self.packages.${system}.native}/bin/mtg-scraper";
          };

          nativeRelease = {
            type = "app";
            program = "${self.packages.${system}.nativeRelease}/bin/mtg-scraper";
          };

          uv = {
            type = "app";
            program = "${self.packages.${system}.uv}/bin/mtg-scraper-uv";
          };
        };
      }
    ) // {
      # Export NixOS module
      nixosModules.default = nixosModule;
      nixosModules.mtg-scraper = nixosModule;
    };
}
