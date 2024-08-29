{
  description = "Manga and comic downloader";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs";

  outputs = { self, nixpkgs }:
  let
    pkgs = nixpkgs.legacyPackages.x86_64-linux;
    pyPkgs = pkgs.python312Packages;
    pyproject = (pkgs.lib.trivial.importTOML ./pyproject.toml).project;
    names = pyproject.dependencies;
    packages = builtins.attrValues (pkgs.lib.attrsets.getAttrs names pyPkgs);
    deps = [ pyPkgs.setuptools pyPkgs.setuptools-scm ] ++ packages;
    typing-deps = deps ++ [ pyPkgs.mypy pyPkgs.types-beautifulsoup4 ];
  in
  {
    packages.x86_64-linux.default = pyPkgs.buildPythonApplication {
      name = "comic-dl";
      version = pyproject.version;
      pyproject = true;
      src = ./.;
      propagatedBuildInputs = deps;
      checkPhase = "python -m unittest";
    };

    checks.x86_64-linux = {
      mypy = pkgs.runCommandLocal "mypy" {
        buildInputs = [ (pkgs.python312.withPackages (_: typing-deps)) ];
      } "cd ${self} && mypy && touch $out";
      pycodestyle = pkgs.runCommandLocal "pycodestyle" {} ''
        ${pkgs.python312Packages.pycodestyle}/bin/pycodestyle ${self}
        touch $out
      '';
    };
  };
}
