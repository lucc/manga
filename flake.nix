{
  description = "Manga and comic downloader";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs";

  outputs = { self, nixpkgs }:
  let
    pkgs = nixpkgs.legacyPackages.x86_64-linux;
    pythonPackages = pkgs.python3Packages;
    pyproject = (pkgs.lib.trivial.importTOML ./pyproject.toml).project;
  in
  {
    packages.x86_64-linux = rec {

      default = pythonPackages.buildPythonApplication {
        name = "comic-dl";
        version = pyproject.version;
        pyproject = true;
        src = ./.;
        propagatedBuildInputs = let
          names = pyproject.dependencies;
          packages = builtins.attrValues (pkgs.lib.attrsets.getAttrs names pythonPackages);
        in [ pythonPackages.setuptools ] ++ packages;
        checkPhase = "python -m unittest";
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
