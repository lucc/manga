{
  description = "Manga and comic downloader";

  outputs = { self, nixpkgs }:
  let
    pkgs = nixpkgs.legacyPackages.x86_64-linux;
    pythonPackages = pkgs.python3Packages;
  in
  {
    packages.x86_64-linux = rec {

      default = pythonPackages.buildPythonApplication {
        name = "comic-dl";
        version = "dev";
        format = "pyproject";
        src = ./.;
        propagatedBuildInputs = with pythonPackages; [
          beautifulsoup4 lxml requests setuptools
        ];
        doCheck = false;
      };

      download-all = pkgs.writeShellScriptBin "download-all" ''
        for f in downloads/*/state.pickle; do
          ${default}/bin/comic-dl -d "''${f%/state.pickle}" --resume
        done
      '';

      loop = pkgs.writeShellScriptBin "loop" ''
        until
          ${download-all}/bin/download-all 2>&1 \
          | awk '/->/{e=1}{print}END{exit e}'
        do
          true
        done
      '';
    };
  };
}
