# Independent synthetic research fixture

`research_demo_v3.json` is a deterministic, source-controlled fixture queried by the researcher-only API. It contains twelve invented subjects with one invented observation each, two missing values, and a mean of 3.5 across ten observed values. Cohorts A and B each have six rows and five observed values. These data are independent of patient records and provide no clinical evidence. No account identities or credentials are included.

This restores the missing fixture required by `cc_api.research_demo_v3`. The API retains role checks, minimum-cell suppression, blocked date slicing and aggregate-only CSV export.
