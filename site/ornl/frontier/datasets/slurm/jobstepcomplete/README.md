# slurm/jobstepcomplete
This stream contains all job steps that run on frontier. The data comes from SLURM `sacct` queries.
It's identical to the `jobsteplive` dataset except its filtered to only contain a single record per
job step. This means that job steps will not show up in this dataset until they are complete. If you
need to be able to see currently running jobs steps, use `jobsteplive`.

- Saved: `s3a://<your-bucket>-sens/tier0/frontier/slurm/jobstepcomplete` as parquets
- Stream: `sens-src-event-frontier-slurmjobstepcomplete` as JSON
- Size: 512 Kib/day

## Schema

- job_id
    - type: STRING
- account
    - type: STRING
- group
    - type: STRING
- user
    - type: STRING
- time_submission
    - type: TIMESTAMP
- step_id
    - type: STRING
- step_name
    - type: STRING
- state
    - type: STRING
- time_start
    - type: TIMESTAMP
- time_end
    - type: TIMESTAMP
- time_elapsed
    - type: DOUBLE
- exit_code_return_code
    - type: BIGINT
- exit_code_status
    - type: STRING
- kill_request_user
    - type: STRING
- task_distribution
    - type: STRING
- tasks_count
    - type: BIGINT
- node_count
    - type: BIGINT
- node_ranges
    - type: STRING
- xnames
    - type: ARRAY<STRING>
- energy_consumed
    - type: DOUBLE
- allocation_id
    - type: STRING
- time_snapshot
    - type: TIMESTAMP

## Stats

|name                 |min      |max        |mean       |median|stddev     |
|---------------------|---------|-----------|-----------|------|-----------|
|time_elapsed         |0        |37357      |3514.67    |2814  |3803.91    |
|exit_code_return_code|0        |255        |11.05      |0     |42.47      |
|tasks_count          |1        |11664      |249.46     |8     |1312.61    |
|node_count           |1        |1641       |71.39      |1     |300.21     |
|energy_consumed      |-13759549|12082701255|70297741.64|684678|480408294.6|
