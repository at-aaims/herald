# Frontier

## Generating Fake Data
To generate fake Frontier data matching the schema of the Frontier jobsummary dataset, use
`generate_frontier_job_data.py`.

`analyze_frontier_job_data.py` analyzes the real jobsummary data and outputs a `stats.json` file
that contains the min/max/std etc. of all the jobsummary columns. `generate_frontier_job_data.py`
uses the `stats.json` file to compute the ranges for the randomly generated data. We already have
a `stats.json` file generated so you shouldn't need to re-run this unless you want to update the
`stats.json`.
