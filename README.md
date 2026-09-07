# Consumer Complaint Analytics

Two projects on the same real dataset (live CFPB consumer complaint data), previously separate repositories, consolidated here (with full commit history preserved via `git subtree`) to tell the actual end-to-end story: ingest and warehouse the data, then classify it.

## [Pipeline](pipeline/) — dbt + DuckDB

Ingests live CFPB complaint data through a tested dbt + DuckDB pipeline: staging models dedupe templated/mass-filed complaints and catch data-integrity issues (15 automated tests), rolling up into 3 dimensional marts with a [generated docs site](https://saijignas.github.io/Complaint-Analytics-Pipeline/) showing full model lineage.

## [Classification](classification/) — ML vs. LLM

Classifies the same complaint data into product categories: a classical TF-IDF + logistic regression baseline (macro-F1 0.84, cross-validated and held-out) benchmarked against zero-shot Gemini classification on identical held-out rows, comparing accuracy, latency, and output reliability rather than picking a single "best" model.

---

Each subdirectory is self-contained with its own README, dependencies, and test suite — see the linked READMEs above for setup instructions and full results.
