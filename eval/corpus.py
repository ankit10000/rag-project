"""
Phase 2 evaluation fixture: a small synthetic multi-document corpus plus a
fixed query set. It is loaded ONLY into a scratch database (never into rag_db).

Relevance is judged at chunk level and is chunking independent: a retrieved
chunk is relevant to a gold item when it belongs to the gold document and its
text contains the gold span (case-insensitive). This lets different chunking
configurations be compared on the same dataset.
"""

DOCS = {
    "network_security_handbook.pdf": [
        "Transport Layer Security (TLS) encrypts traffic between a client and a server. "
        "TLS 1.3 removed legacy ciphers and reduced the handshake to a single round trip. "
        "Mutual TLS (mTLS) additionally requires the client to present a certificate, which is "
        "common for service to service calls inside a cluster. Certificates must be renewed "
        "before the 90 day expiry window used by the internal certificate authority.",

        "A firewall filters packets using rules based on source address, destination address and port. "
        "A stateful firewall tracks connections, while an intrusion detection system (IDS) inspects "
        "traffic for known attack signatures. The default policy on the perimeter firewall is deny all "
        "inbound traffic except port 443. A virtual private network (VPN) tunnels remote staff into the "
        "corporate network using WireGuard.",

        "Distributed denial of service (DDoS) attacks flood a service with traffic until it stops "
        "responding. Mitigation uses rate limiting, anycast scrubbing centers and automatic traffic "
        "blackholing. The zero trust model assumes no device is trusted by default, so every request is "
        "authenticated and authorised regardless of network location. Security audits are performed "
        "every six months by an external auditor.",
    ],
    "database_operations_guide.pdf": [
        "PostgreSQL uses multiversion concurrency control, so updated rows leave dead tuples behind. "
        "The VACUUM command reclaims that space and autovacuum runs it automatically. "
        "The write ahead log (WAL) records every change before it is applied to the data files, which "
        "allows crash recovery and streaming replication to a standby server. The default checkpoint "
        "interval is five minutes.",

        "The pgvector extension adds a vector column type and distance operators. Approximate nearest "
        "neighbour search can use an HNSW index or an IVFFlat index. HNSW builds a layered proximity "
        "graph, gives better recall at query time and is slower to build, while IVFFlat clusters vectors "
        "into lists and needs training data before the index is created. Cosine distance is written as "
        "the <=> operator.",

        "Backups are taken nightly with pg_dump in custom format and stored for 30 days. "
        "A restore drill is carried out every quarter to prove the backups are usable. "
        "Application servers connect through PgBouncer, a connection pooler, because each PostgreSQL "
        "connection costs about ten megabytes of memory. The pool size is capped at 50 connections per "
        "application instance.",
    ],
    "machine_learning_primer.pdf": [
        "An embedding maps a piece of text to a dense vector so that texts with similar meaning end up "
        "close together. Similarity is usually measured with cosine similarity, which compares the angle "
        "between two vectors and ignores their length. Sentence transformers produce these vectors "
        "with a transformer encoder and mean pooling over the token outputs.",

        "BM25 is a ranking function that scores documents by term frequency, inverse document frequency "
        "and document length normalisation. It rewards exact keyword matches and works well for rare "
        "technical terms. Reciprocal rank fusion (RRF) merges several ranked lists by summing 1 divided by "
        "k plus the rank of each item, with k commonly set to 60. A cross encoder reads the query and a "
        "passage together and outputs a relevance score, which is slower but more precise than a bi encoder.",

        "Overfitting happens when a model memorises training examples and performs poorly on unseen data. "
        "Regularisation, early stopping and more training data reduce it. The learning rate controls the "
        "size of each gradient descent step; a value that is too large makes training diverge. "
        "Evaluation uses held out data, and common retrieval metrics are recall at K, precision at K and "
        "mean reciprocal rank (MRR).",
    ],
    "hr_policy_manual.pdf": [
        "Annual leave: every full time employee receives 24 days of paid annual leave per calendar year. "
        "Unused leave of up to 5 days may be carried over into the next year. Sick leave is separate and "
        "requires a medical certificate after three consecutive days. This policy is referenced as "
        "POL-HR-014.",

        "Remote work: employees may work from home for up to three days per week with manager approval. "
        "A stipend of 40 dollars per month covers internet costs. Equipment such as laptops and monitors "
        "remains company property and must be returned on the last working day. This policy is referenced "
        "as POL-HR-022.",

        "Probation and notice: new hires serve a probation period of six months. During probation either "
        "side may end the contract with two weeks notice. After confirmation the notice period is two "
        "months. Expense reimbursement claims must be filed within 30 days with original receipts, under "
        "policy POL-HR-031.",
    ],
    "cloud_cost_report_2026.pdf": [
        "Q3 2026 cloud spend totalled 1.82 million dollars, which is 7 percent above the approved budget. "
        "Compute accounted for 61 percent of the bill, object storage for 14 percent and data transfer "
        "for 9 percent. The largest single driver of the overrun was an unplanned batch workload "
        "running on on demand instances.",

        "Moving stateless workers to spot instances cut compute cost by 38 percent in the pilot team. "
        "Spot capacity can be reclaimed with a two minute warning, so jobs must checkpoint their state. "
        "A one year Savings Plan covering 60 percent of the steady baseline is recommended. "
        "The FinOps group reviews cost anomalies every Monday.",

        "S3 storage costs fell after lifecycle rules moved logs older than 90 days to the infrequent "
        "access tier and then to Glacier after 365 days. Egress charges remain high for the analytics "
        "export job. The target for Q4 is a total spend of 1.65 million dollars, tracked by the tag "
        "cost-center on every resource.",
    ],
    "incident_postmortems.pdf": [
        "Incident INC-2041: on 14 March the checkout service returned errors for 47 minutes. The root "
        "cause was an expired TLS certificate on the payment gateway, which produced error code "
        "ERR-4096 in the client logs. The fix was to renew the certificate and add an expiry alert "
        "30 days ahead of renewal.",

        "Incident INC-2057: a bad configuration push doubled the connection count and exhausted the "
        "database connection pool. Service recovered after a rollback to the previous release. Mean "
        "time to recovery (MTTR) for the quarter was 38 minutes. The service level objective (SLO) for "
        "availability is 99.9 percent per month.",

        "Action items from the quarter: introduce canary deployments for configuration changes, add a "
        "load test to the release pipeline and rehearse the rollback runbook. The on call engineer must "
        "acknowledge a page within five minutes. Postmortems are blameless and are published within "
        "three working days of resolution.",
    ],
    "api_reference_v2.pdf": [
        "Authentication uses OAuth2 with the authorization code flow. Access tokens are JSON Web Tokens "
        "(JWT) signed with RS256 and expire after 3600 seconds. A refresh token can be exchanged for a "
        "new access token and expires after 30 days. Send the token in the Authorization header as a "
        "Bearer credential.",

        "Rate limiting: each API key may make 600 requests per minute. When the limit is exceeded the "
        "server responds with status 429 and a Retry-After header. List endpoints use cursor based "
        "pagination; pass the next_cursor value from the previous response and a page size of at most "
        "100 items.",

        "Webhooks deliver events to your endpoint with an HTTP POST. Each request carries an "
        "X-Signature header containing an HMAC SHA-256 signature of the body, which you must verify "
        "before trusting the payload. Failed deliveries are retried with exponential backoff for up to "
        "24 hours. Status 422 means the request body failed validation.",
    ],
    "candidate_list_2026.pdf": [
        "Shortlisted candidates, Department of Soil Science. Application PHD26031 Meera Kapoor, "
        "daughter of Sh. Ravi Kapoor, category GEN, qualified UGC NET JRF. Application PHD26044 Imran "
        "Qureshi, son of Sh. Salim Qureshi, category OBC, qualified CSIR NET. Application PHD26052 "
        "Lakshmi Iyer, daughter of Sh. Gopal Iyer, category SC, qualified GATE.",

        "Shortlisted candidates, Department of Hydrology. Application PHD26067 Arjun Nair, son of "
        "Sh. Mohan Nair, category GEN, qualified UGC NET JRF. Application PHD26071 Sana Sheikh, "
        "daughter of Sh. Yusuf Sheikh, category EWS, qualified CSIR NET. Interviews for this department "
        "will be held on 12 October in room 204.",

        "General instructions: candidates must bring original certificates and one photo identity card "
        "to the interview. Travel allowance is not payable. For queries contact the admissions office at "
        "0135-2224433 or write to the Ph.D. section. The list may be withdrawn at any time.",
    ],
}

# (query, kind, gold, doc_filter)
#   gold: list of (document, span) items; every item is a distinct needed fact.
#   kind: semantic | keyword | abbrev | multi | metadata | short | noanswer
QUERIES = [
    # ---- semantic (paraphrased, little keyword overlap) -------------------
    ("How can a server prove its identity and keep traffic private?", "semantic",
     [("network_security_handbook.pdf", "TLS 1.3 removed legacy ciphers")], None),
    ("What happens to old row versions after an update in the database?", "semantic",
     [("database_operations_guide.pdf", "leave dead tuples behind")], None),
    ("How do computers represent the meaning of a sentence as numbers?", "semantic",
     [("machine_learning_primer.pdf", "maps a piece of text to a dense vector")], None),
    ("How many vacation days do staff get each year?", "semantic",
     [("hr_policy_manual.pdf", "24 days of paid annual leave")], None),
    ("Why did the online shop stop working for most of an hour in March?", "semantic",
     [("incident_postmortems.pdf", "expired TLS certificate")], None),
    ("How can I cut compute expenses using interruptible machines?", "semantic",
     [("cloud_cost_report_2026.pdf", "spot instances cut compute cost by 38 percent")], None),
    ("What should I do to be sure a callback request really came from the platform?", "semantic",
     [("api_reference_v2.pdf", "HMAC SHA-256 signature")], None),
    ("Which policy lets people work outside the office?", "semantic",
     [("hr_policy_manual.pdf", "work from home for up to three days")], None),
    # ---- exact keyword / identifier --------------------------------------
    ("ERR-4096", "keyword",
     [("incident_postmortems.pdf", "ERR-4096")], None),
    ("POL-HR-031", "keyword",
     [("hr_policy_manual.pdf", "POL-HR-031")], None),
    ("PHD26052", "keyword",
     [("candidate_list_2026.pdf", "PHD26052 Lakshmi Iyer")], None),
    ("INC-2057", "keyword",
     [("incident_postmortems.pdf", "Incident INC-2057")], None),
    ("Who is candidate PHD26067?", "keyword",
     [("candidate_list_2026.pdf", "PHD26067 Arjun Nair")], None),
    ("What is the phone number of the admissions office?", "keyword",
     [("candidate_list_2026.pdf", "0135-2224433")], None),
    ("X-Signature header", "keyword",
     [("api_reference_v2.pdf", "X-Signature header")], None),
    ("WireGuard", "keyword",
     [("network_security_handbook.pdf", "WireGuard")], None),
    # ---- abbreviations / technical terms ---------------------------------
    ("What is HNSW?", "abbrev",
     [("database_operations_guide.pdf", "HNSW builds a layered proximity graph")], None),
    ("What does RRF stand for and what is k?", "abbrev",
     [("machine_learning_primer.pdf", "Reciprocal rank fusion (RRF)")], None),
    ("What is mTLS used for?", "abbrev",
     [("network_security_handbook.pdf", "Mutual TLS (mTLS)")], None),
    ("What is the MTTR for the quarter?", "abbrev",
     [("incident_postmortems.pdf", "38 minutes")], None),
    ("How long does a JWT access token live?", "abbrev",
     [("api_reference_v2.pdf", "expire after 3600 seconds")], None),
    ("What is the WAL?", "abbrev",
     [("database_operations_guide.pdf", "write ahead log (WAL)")], None),
    ("What does the IDS do?", "abbrev",
     [("network_security_handbook.pdf", "intrusion detection system (IDS)")], None),
    ("What is the SLO for availability?", "abbrev",
     [("incident_postmortems.pdf", "99.9 percent per month")], None),
    # ---- multi-concept / compound ----------------------------------------
    ("Compare HNSW and IVFFlat indexes and explain what pg_dump is used for.", "multi",
     [("database_operations_guide.pdf", "HNSW builds a layered proximity graph"),
      ("database_operations_guide.pdf", "pg_dump in custom format")], None),
    ("What is the annual leave allowance and how long is the probation period?", "multi",
     [("hr_policy_manual.pdf", "24 days of paid annual leave"),
      ("hr_policy_manual.pdf", "probation period of six months")], None),
    ("Explain BM25 and also how cross encoders differ from bi encoders.", "multi",
     [("machine_learning_primer.pdf", "BM25 is a ranking function"),
      ("machine_learning_primer.pdf", "A cross encoder reads the query")], None),
    ("What was the Q3 cloud spend and what is the Q4 target?", "multi",
     [("cloud_cost_report_2026.pdf", "1.82 million dollars"),
      ("cloud_cost_report_2026.pdf", "1.65 million dollars")], None),
    ("What caused INC-2041 and what did the INC-2057 rollback fix?", "multi",
     [("incident_postmortems.pdf", "expired TLS certificate"),
      ("incident_postmortems.pdf", "rollback to the previous release")], None),
    ("What is the API rate limit and how is pagination done?", "multi",
     [("api_reference_v2.pdf", "600 requests per minute"),
      ("api_reference_v2.pdf", "cursor based")], None),
    # ---- metadata (document filter applied) ------------------------------
    ("What is the notice period?", "metadata",
     [("hr_policy_manual.pdf", "After confirmation the notice period is two")], "hr_policy_manual.pdf"),
    ("How long are backups kept?", "metadata",
     [("database_operations_guide.pdf", "stored for 30 days")], "database_operations_guide.pdf"),
    ("What is the expiry period of the refresh token?", "metadata",
     [("api_reference_v2.pdf", "expires after 30 days")], "api_reference_v2.pdf"),
    ("When is the interview?", "metadata",
     [("candidate_list_2026.pdf", "12 October in room 204")], "candidate_list_2026.pdf"),
    # ---- short queries ----------------------------------------------------
    ("HNSW", "short",
     [("database_operations_guide.pdf", "HNSW builds a layered proximity graph")], None),
    ("JWT", "short",
     [("api_reference_v2.pdf", "JSON Web Tokens")], None),
    ("probation", "short",
     [("hr_policy_manual.pdf", "probation period of six months")], None),
    ("Glacier", "short",
     [("cloud_cost_report_2026.pdf", "Glacier after 365 days")], None),
    # ---- no relevant document --------------------------------------------
    ("Who won the football world cup in 2022?", "noanswer", [], None),
    ("Give me a recipe for lasagna.", "noanswer", [], None),
    ("What is the capital of Australia?", "noanswer", [], None),
    ("How do I repair a bicycle tyre?", "noanswer", [], None),
]


# ---------------------------------------------------------------------------
# Distractors: deterministic filler documents that share the domain vocabulary
# (and look-alike identifiers) with the real corpus but never contain a gold
# fact. They make top-K retrieval non-trivial and double as the "large
# document" fixture.
# ---------------------------------------------------------------------------
import random

_TEAMS = ["platform team", "audit group", "regional office", "vendor", "review board",
          "operations desk", "finance group", "security guild", "support rota", "data team"]
_TOPICS = ["TLS certificate", "database index", "embedding model", "leave request",
           "cloud invoice", "API token", "firewall rule", "webhook retry", "backup job",
           "incident ticket", "vector column", "connection pool", "probation review",
           "storage tier", "rate limit", "candidate file", "deployment pipeline",
           "keyword ranking", "replication slot", "expense claim"]
_VERBS = ["reviewed", "updated", "archived", "escalated", "documented", "measured",
          "postponed", "approved", "rejected", "simulated"]
_MEASURES = ["latency", "capacity", "retention", "coverage", "cost", "throughput",
             "accuracy", "backlog", "risk", "priority"]
_TEMPLATES = [
    "The {team} {verb} the {topic} and recorded the {measure} for the next planning cycle.",
    "During the quarterly session the {team} {verb} every {topic} related to {measure}.",
    "A note on the {topic}: the {team} {verb} it twice, and the {measure} stayed within the agreed band.",
    "Nobody on the {team} {verb} the {topic} before the {measure} figures were collected.",
    "Open question for the {team}: should the {topic} be {verb} when {measure} changes?",
    "Reference {ref}: the {topic} was {verb} by the {team} without any change to {measure}.",
    "The {topic} summary lists {n} items; the {team} {verb} {m} of them and left the {measure} untouched.",
]


def make_distractors(n_docs: int = 120, pages_per_doc: int = 3, seed: int = 7) -> dict:
    rng = random.Random(seed)
    docs = {}

    for d in range(n_docs):
        pages = []
        for _ in range(pages_per_doc):
            sentences = []
            for _ in range(8):
                ref = rng.choice([
                    f"ERR-{rng.randint(1000, 4999)}", f"POL-HR-{rng.randint(1, 99):03d}",
                    f"INC-{rng.randint(1000, 3999)}", f"PHD26{rng.randint(100, 999)}",
                ])
                if ref in ("ERR-4096", "POL-HR-031", "INC-2057", "INC-2041", "PHD26052", "PHD26067"):
                    ref = "REF-0000"
                sentences.append(rng.choice(_TEMPLATES).format(
                    team=rng.choice(_TEAMS), verb=rng.choice(_VERBS),
                    topic=rng.choice(_TOPICS), measure=rng.choice(_MEASURES),
                    ref=ref, n=rng.randint(3, 40), m=rng.randint(1, 3),
                ))
            pages.append(" ".join(sentences))
        docs[f"filler_{d:03d}.pdf"] = pages

    return docs
