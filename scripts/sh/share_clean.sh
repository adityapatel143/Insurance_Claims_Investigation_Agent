#!/usr/bin/env bash
# Prepare the project for sharing: remove local secrets/config and generated files, or build an archive.
# Usage: scripts/sh/share_clean.sh [--yes] [--archive <file.tar.gz>]
#   (no flags)          dry run: list what would be removed
#   --yes               delete the listed files and folders (local config such as .env and tfvars included)
#   --archive <file>    write a tar.gz of tracked + untracked non-ignored files; deletes nothing
# Terraform state (*.tfstate) is never deleted: it may be the only record of deployed resources.
source "$(dirname "$0")/_lib.sh"
usage_if_help "${1:-}"

mode=dry-run
archive=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes) mode=delete ;;
    --archive)
      [ -n "${2:-}" ] || die "--archive needs a file name"
      mode=archive
      archive="$2"
      shift
      ;;
    *) die "unknown option '$1' (see --help)" ;;
  esac
  shift
done

if [ "$mode" = archive ]; then
  require_cmd git tar
  case "$archive" in
    *.tar.gz | *.tgz) ;;
    *) die "archive name must end in .tar.gz or .tgz" ;;
  esac
  case "$archive" in
    /*) ;;
    *) archive="$REPO_ROOT/$archive" ;;
  esac
  # .gitignore already excludes secrets, state, caches, and build output.
  git ls-files -z --cached --others --exclude-standard |
    while IFS= read -r -d '' path; do
      [ -e "$path" ] && printf '%s\0' "$path"
    done |
    tar -czf "$archive" --null -T -
  echo "Wrote $archive ($(tar -tzf "$archive" | wc -l | tr -d ' ') files). Nothing was deleted."
  exit 0
fi

dirs=(.venv node_modules .terraform build dist .pytest_cache .mypy_cache .ruff_cache htmlcov __pycache__)
files=(.env terraform.tfvars common.tfvars backend.hcl tfplan crash.log .coverage coverage.xml .DS_Store
  .terraform.tfstate.lock.info)

find_args=()
for d in "${dirs[@]}"; do find_args+=(-o -type d -name "$d" -prune -print0); done
for f in "${files[@]}"; do find_args+=(-o -type f -name "$f" -print0); done
find_args+=(-o -type f -name '.env.*' ! -name '.env.example' -print0)
find_args+=(-o -type f \( -name '*.tfplan' -o -name '*.py[cod]' \) -print0)
find_args+=(-o -type f -path './infra/modules/*/.terraform.lock.hcl' -print0)

targets=()
while IFS= read -r -d '' path; do targets+=("$path"); done < <(find . -path ./.git -prune "${find_args[@]}")

state_files=()
while IFS= read -r path; do state_files+=("$path"); done < <(
  find . -path ./.git -prune -o -type f \( -name '*.tfstate' -o -name '*.tfstate.*' \) -print
)

if [ ${#targets[@]} -eq 0 ]; then
  echo "Nothing to clean."
else
  echo "Would remove:"
  printf '  %s\n' "${targets[@]}"
fi
if [ ${#state_files[@]} -gt 0 ]; then
  echo "Kept (Terraform state; do not share, may describe your account):"
  printf '  %s\n' "${state_files[@]}"
fi

if [ "$mode" = dry-run ]; then
  echo "Dry run. Re-run with --yes to delete, or use --archive <file.tar.gz> to share without deleting."
  exit 0
fi

[ ${#targets[@]} -eq 0 ] || rm -rf -- "${targets[@]}"
echo "Removed ${#targets[@]} paths. Recreate local config from the *.example files; run scripts/sh/sync.sh to reinstall."
