"""Create (or recreate) the retrieval index in the OpenSearch Serverless collection.

Example:
  uv run python scripts/create_index.py \
    --endpoint "$(terraform -chdir=infra/environments/dev/platform output -raw \
        opensearch_endpoint)" \
    --index claims-guidance --dimensions 1024
"""

import argparse

from _common import host_of, resolve_region
from claims_investigator.gateways.opensearch import OpenSearchVectorSearch, build_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--endpoint", required=True, help="Collection endpoint URL or host.")
    parser.add_argument(
        "--index", default="claims-guidance", help="Index name (CLAIMS_OPENSEARCH_INDEX)."
    )
    parser.add_argument("--dimensions", type=int, default=1024, help="Embedding vector dimension.")
    parser.add_argument("--region", help="AWS Region (defaults to AWS_REGION or the CLI profile).")
    parser.add_argument(
        "--recreate", action="store_true", help="Delete the index first (removes all chunks)."
    )
    args = parser.parse_args()

    client = build_client(host_of(args.endpoint), resolve_region(args.region))
    search = OpenSearchVectorSearch(client, args.index)
    if args.recreate and search.delete_index():
        print(f"Deleted index {args.index}")
    created = search.create_index(args.dimensions)
    print(
        f"{'Created' if created else 'Index already exists:'} {args.index} "
        f"(dimension {args.dimensions})"
    )


if __name__ == "__main__":
    main()
