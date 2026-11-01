# slurm/joblive
This stream contains all jobs that run on frontier. The data comes from SLURM `sacct` queries.
Its saved as "snapshots" of complete job state roughly every 30 seconds, so each job will show up
multiple times, with the `time_snapshot` field saying when the snapshot was taken. If you just want
one record per job with the final state, use `jobcomplete`.

- Saved: `s3a://<your-bucket>-sens/tier0/frontier/slurm/joblive` as parquets
- Stream: `sens-src-event-frontier-slurmjoblive` as JSON
- Size: 50 MiB/day

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

|name                       |min|max     |mean      |median|stddev     |
|---------------------------|---|--------|----------|------|-----------|
|time_limit                 |10 |10080   |288.38    |120   |968.45     |
|time_elapsed               |0  |73395723|2012533.41|0     |11829686.51|
|node_count                 |0  |2048    |29.6      |0     |143.76     |
|batch_time_elapsed         |0  |73395723|2012533.41|0     |11829686.51|
|batch_exit_code_return_code|0  |250     |0.12      |0     |4.41       |
