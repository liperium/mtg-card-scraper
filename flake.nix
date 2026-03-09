{
  description = "MTG Card Scraper - Streamlit app for scraping card prices";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Python environment with all dependencies
        pythonEnv = pkgs.python313.withPackages (ps: with ps; [
          streamlit
          pandas
          selenium
        ]);

        # Script to run the app with native Python
        runScript = pkgs.writeShellScriptBin "mtg-scraper" ''
          cd ${./.}
          export PYTHONPATH="${./.}:$PYTHONPATH"
          export PATH="${pkgs.chromium}/bin:${pkgs.chromedriver}/bin:$PATH"
          export CHROME_BIN="${pkgs.chromium}/bin/chromium"
          export CHROMEDRIVER_PATH="${pkgs.chromedriver}/bin/chromedriver"
          ${pythonEnv}/bin/streamlit run app.py "$@"
        '';

        # Script to run the app with uv
        uvRunScript = pkgs.writeShellScriptBin "mtg-scraper-uv" ''
          cd ${./.}
          export PATH="${pkgs.chromium}/bin:${pkgs.chromedriver}/bin:$PATH"
          export CHROME_BIN="${pkgs.chromium}/bin/chromium"
          export CHROMEDRIVER_PATH="${pkgs.chromedriver}/bin/chromedriver"
          ${pkgs.uv}/bin/uv run streamlit run app.py "$@"
        '';

      in
      {
        packages = {
          # Default: Use uv (matches your current setup)
          default = pkgs.writeShellScriptBin "mtg-scraper" ''
            cd ${./.}
            export PATH="${pkgs.chromium}/bin:${pkgs.chromedriver}/bin:$PATH"
            export CHROME_BIN="${pkgs.chromium}/bin/chromium"
            export CHROMEDRIVER_PATH="${pkgs.chromedriver}/bin/chromedriver"
            ${pkgs.uv}/bin/uv run streamlit run app.py "$@"
          '';

          # Alternative: Native Python with modules
          native = runScript;

          # Explicit uv version
          uv = uvRunScript;
        };

        # Development shell with all tools
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.uv
            pkgs.chromium
            pkgs.chromedriver
          ];

          shellHook = ''
            echo "MTG Card Scraper development environment"
            echo "Run 'streamlit run app.py' to start the app"
            echo "Or use 'uv run streamlit run app.py'"

            # Set Chrome/Chromium and chromedriver paths for Selenium
            export CHROME_BIN="${pkgs.chromium}/bin/chromium"
            export CHROMEDRIVER_PATH="${pkgs.chromedriver}/bin/chromedriver"
            export PATH="${pkgs.chromium}/bin:${pkgs.chromedriver}/bin:$PATH"
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

          uv = {
            type = "app";
            program = "${self.packages.${system}.uv}/bin/mtg-scraper-uv";
          };
        };
      }
    );
}
