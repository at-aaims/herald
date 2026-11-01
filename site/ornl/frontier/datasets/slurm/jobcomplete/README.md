# slurm/jobcomplete
This stream contains all jobs that run on frontier. The data comes from SLURM `sacct` queries. It's
identical to the `joblive` dataset except its filtered to only contain a single record per job. This
means that jobs will not show up in this dataset until they are complete. If you need to be able to
see currently running jobs, use `joblive`.

- Saved: `s3a://<your-bucket>-sens/tier0/frontier/slurm/jobcomplete` as parquets
- Stream: `sens-src-event-frontier-slurmjobcomplete` as JSON
- Size: 512 Kib/day

## Schema

- slurm_version
    - type: STRING
- job_id
    - type: STRING
- account
    - type: STRING
- group
    - type: STRING
- user
    - type: STRING
- name
    - type: STRING
- working_directory
    - type: STRING
- partition
    - type: STRING
- time_limit
    - type: DOUBLE
- constraints
    - type: STRING
- mcs
    - type: STRING
- time_submission
    - type: TIMESTAMP
- time_eligible
    - type: TIMESTAMP
- time_start
    - type: TIMESTAMP
- time_end
    - type: TIMESTAMP
- time_elapsed
    - type: DOUBLE
- node_count
    - type: BIGINT
- node_ranges
    - type: STRING
- xnames
    - type: ARRAY<STRING>
- state_current
    - type: STRING
- state_reason
    - type: STRING
- batch_time_start
    - type: TIMESTAMP
- batch_time_end
    - type: TIMESTAMP
- batch_time_elapsed
    - type: DOUBLE
- batch_state
    - type: STRING
- batch_exit_code_return_code
    - type: BIGINT
- batch_exit_code_status
    - type: STRING
- allocation_id
    - type: STRING
- time_snapshot
    - type: TIMESTAMP

## Stats

|name                       |min|max  |mean   |median|stddev |
|---------------------------|---|-----|-------|------|-------|
|time_limit                 |10 |719  |82.06  |120   |64.84  |
|time_elapsed               |0  |37357|2918.55|828   |3731.27|
|node_count                 |0  |1641 |117.31 |1     |382.14 |
|batch_time_elapsed         |0  |37357|2918.65|828   |3731.28|
|batch_exit_code_return_code|0  |250  |31.18  |0     |63.92  |

