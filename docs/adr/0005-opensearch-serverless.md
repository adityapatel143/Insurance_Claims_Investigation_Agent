# ADR 0005: OpenSearch Serverless for retrieval

- Status: Accepted
- Date: 2026-09-30

## Context

The agent retrieves synthetic investigation guidance and synthetic historical claims. It needs vector
search with metadata filters, AWS-owned encryption, and no anonymous access, at low
operational overhead.

## Decision

1. Use an Amazon OpenSearch Serverless collection of type `VECTORSEARCH`, one per environment.
2. Use AWS-owned encryption without a customer-managed key. Data-access policy grants only the tools Lambda role
   (read) and a named indexer principal (write/index management). Every request is SigV4-signed;
   anonymous access is not possible.
3. Network policy: IAM-authenticated public endpoint by default (`dev`); optional VPC endpoint with public
   access disabled (`enable_vpc_endpoint`, recommended for `prod`).
4. One index (name configurable) with explicit mappings: `document_id`, `chunk_id`, `source_type`
   (`guidance` | `historical_claim`), `source_uri`, `claim_type`, `text`, `metadata`, and a `knn_vector`
   field whose dimension equals the configured embedding model's output dimension.
5. Hybrid retrieval: k-NN query combined with a lexical `match` on `text`, filtered by `source_type` and
   `claim_type`. Scores are returned internally; an empty result is returned as empty — never synthesized.
6. Index creation and ingestion are CLI scripts (`scripts/create_index.py`, `scripts/seed_sample_data.py`).

## Consequences

- OpenSearch Serverless has a minimum OCU charge even when idle; documented in `docs/cost-considerations.md`.
- Private access requires the optional VPC endpoint and VPC-attached Lambdas.

## Alternatives considered

- **OpenSearch Service managed domain in a VPC:** more control, but requires VPC, subnets, and
  VPC-attached Lambdas for every environment.
- **Bedrock Knowledge Bases:** would hide retrieval scoring and chunk metadata needed for evidence references.
