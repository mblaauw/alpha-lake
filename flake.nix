{
  description = "Alpha-Lake — market-data lakehouse";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = nixpkgs.legacyPackages.${system}; in {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python314
            uv
            docker-compose
          ];
          shellHook = ''
            echo "Alpha-Lake development shell"
            echo "Run 'just up' to start the stack"
          '';
        };
      });
}
