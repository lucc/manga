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
        in [ pythonPackages.setuptools pythonPackages.setuptools-scm ] ++ packages;
        checkPhase = "python -m unittest";
      };

      download-all = pkgs.writeShellScriptBin "download-all" ''
        dir=''${1?You have to provide a directory as first argument.}
        for f in "$dir"/*/state.pickle; do
          ${default}/bin/comic-dl download --directory "''${f%/state.pickle}" --resume
        done
      '';
    };

    checks.x86_64-linux = {
      mypy = pkgs.runCommandLocal "mypy" {
        buildInputs = [ (pkgs.python3.withPackages (_: typing-deps)) ];
      } "cd ${self} && mypy && touch $out";
      pycodestyle = pkgs.runCommandLocal "pycodestyle" {} ''
        ${pkgs.python3Packages.pycodestyle}/bin/pycodestyle ${self}
        touch $out
      '';
    };
  };
}
