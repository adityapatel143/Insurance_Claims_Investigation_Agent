"""Upload synthetic sample data to S3 `sample-data/` and index guidance and historical examples.

The index must exist first (scripts/create_index.py). Indexing is append-only: re-seed after
`create_index.py --recreate` to avoid duplicate chunks. Newly indexed chunks can take up to about
a minute to become searchable.

Example:
  uv run python scripts/seed_sample_data.py \
    --bucket "$(terraform -chdir=infra/environments/dev/platform output -raw bucket_name)" \
    --endpoint "$(terraform -chdir=infra/environments/dev/platform output -raw opensearch_endpoint)"
"""

import argparse
import mimetypes

import boto3

from _common import SAMPLE_DATA, host_of, read_front_matter, resolve_region
from claims_investigator.gateways.aws import client_config
from claims_investigator.gateways.embeddings import BedrockEmbedder
from claims_investigator.gateways.opensearch import OpenSearchVectorSearch, build_client
from claims_investigator.models.findings import SourceType
from claims_investigator.storage_keys import SAMPLE_DATA_PREFIX

MAX_CHUNK_CHARS = 1200
VALID_CLAIM_TYPES = {"AUTO", "PROPERTY", "TRAVEL", "GENERAL"}
INDEXED_DIRS = ("guidance", "historical")


def chunk_markdown(body: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Group paragraphs into chunks of at most `max_chars`, keeping paragraphs whole."""
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in body.split("\n\n")):
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph[:max_chars]
    if current:
        chunks.append(current)
    return chunks


def upload_sample_files(bucket: str, region: str) -> int:
    s3 = boto3.client("s3", region_name=region, config=client_config())
    count = 0
    for path in sorted(p for p in SAMPLE_DATA.rglob("*") if p.is_file()):
        key = SAMPLE_DATA_PREFIX + path.relative_to(SAMPLE_DATA).as_posix()
        content_type = mimetypes.guess_type(path.name)[0] or "text/plain"
        s3.put_object(Bucket=bucket, Key=key, Body=path.read_bytes(), ContentType=content_type)
        count += 1
    return count


def index_documents(
    search: OpenSearchVectorSearch, embedder: BedrockEmbedder, bucket: str | None
) -> int:
    count = 0
    for directory in INDEXED_DIRS:
        for path in sorted((SAMPLE_DATA / directory).glob("*.md")):
            meta, body = read_front_matter(path)
            source_type = SourceType(meta["source_type"])
            claim_type = meta.get("claim_type", "GENERAL")
            if claim_type not in VALID_CLAIM_TYPES:
                raise SystemExit(f"{path}: unsupported claim_type {claim_type}")
            relative = path.relative_to(SAMPLE_DATA).as_posix()
            uri = (
                f"s3://{bucket}/{SAMPLE_DATA_PREFIX}{relative}"
                if bucket
                else f"repo://sample-data/{relative}"
            )
            for number, text in enumerate(chunk_markdown(body)):
                chunk_id = f"{path.stem}#c{number}"
                search.index_chunk(
                    chunk_id,
                    {
                        "document_id": path.stem,
                        "source_type": str(source_type),
                        "source_uri": uri,
                        "claim_type": claim_type,
                        "title": meta.get("title", path.stem),
                        "text": text,
                        "metadata": {"synthetic": True, "path": relative},
                        "embedding": embedder.embed(text),
                    },
                )
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--endpoint", required=True, help="Collection endpoint URL or host.")
    parser.add_argument("--bucket", help="Data bucket; omit with --skip-s3.")
    parser.add_argument("--index", default="claims-guidance")
    parser.add_argument("--embedding-model-id", default="amazon.titan-embed-text-v2:0")
    parser.add_argument("--dimensions", type=int, default=1024)
    parser.add_argument("--region")
    parser.add_argument(
        "--skip-s3", action="store_true", help="Index only; do not upload files to S3."
    )
    args = parser.parse_args()
    if not args.skip_s3 and not args.bucket:
        parser.error("--bucket is required unless --skip-s3 is set")

    region = resolve_region(args.region)
    if not args.skip_s3:
        print(
            f"Uploaded {upload_sample_files(args.bucket, region)} files to s3://{args.bucket}/{SAMPLE_DATA_PREFIX}"
        )
    search = OpenSearchVectorSearch(build_client(host_of(args.endpoint), region), args.index)
    embedder = BedrockEmbedder(
        boto3.client("bedrock-runtime", region_name=region, config=client_config()),
        args.embedding_model_id,
        args.dimensions,
    )
    print(f"Indexed {index_documents(search, embedder, args.bucket)} chunks into {args.index}")


if __name__ == "__main__":
    main()
