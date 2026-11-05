# Data directory

The A-share data Skill stores its local bar cache under:

```text
<skill>/data/
```

or the path passed with `--data-dir` / `ASHARE_DATA_DIR`.

Raw market data is not committed. Run the skill's `bars` / `update` commands to
populate it, or point `--data-dir` at an existing cache. The distributor must
confirm the data source's redistribution terms before publishing a cache.
