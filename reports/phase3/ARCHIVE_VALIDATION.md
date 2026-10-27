# Clean source/archive validation

Initial clean source commit9ed2803:730 source/instruction files plus generated manifest; CRC/per-file SHA256/case-collision/allowlist validation PASS, no nested archives, no forbidden members. Archive extracted to a private folder without.git, served by actual Flask onlocalhost8772 using a separate new private SQLite workspace. Five short browser cases PASS (health/public contract + incomplete-answer behavior for all four forms),2.00s. No Qwen generation or repeated full regression.

The extracted runner correctly obtains the exact source revision from PACKAGE_MANIFEST.json when Git is absent. Missing phase PROGRESS.md is bootstrapped, all five real results flushed/fsynced. This closes a fresh-archive portability gap in QA tooling; application behavior/clinical rules were not changed. Evidence: raw/fresh-archive-smoke.xml/log and fresh-archive-metadata-bootstrap.json. Only the temporary8772 source-smoke server is stopped afterward; native8769 and Docker8768 remain running.

Final delivery is rebuilt from the final clean documentation/checkpoint commit and independently revalidated; exact commit, file count, archive SHA256 and source-tree hash are in deliverables/RELEASE_CHECKSUMS.json and the generated manifest inside the source ZIP. The earlier staged archive check is retained rather than overwritten as proof of another run.

Separate sanitized QA ZIP contains selected reports, safe numeric/model metadata, ordinary-read CSV and redacted timelines. No DB, generated actor/patient identity file, cookie/header/body capture, invitation token, runtime secret, model weight or private full trace is included. The five requested PNGs remain a separate screenshot ZIP with documented capture limitations.
