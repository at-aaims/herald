# slurm/jobsteplive
This stream contains all job steps that run on frontier. The data comes from SLURM `sacct` queries.
Its saved as "snapshots" of complete job step state roughly every 30 seconds, so each job step will
show up multiple times, with the `time_snapshot` field saying when the snapshot was taken. If you
just want one record per job step with the final state, use `jobstepcomplete`.

- Saved: `s3a://<your-bucket>-sens/tier0/frontier/slurm/jobsteplive` as parquets
- Stream: `sens-src-event-frontier-slurmjobsteplive` as JSON
- Size: 100 MiB/day

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

|name                 |min      |max        |mean     |median|stddev    |
|---------------------|---------|-----------|---------|------|----------|
|time_elapsed         |0        |73382978   |318885.64|2212  |4802623.9 |
|exit_code_return_code|0        |255        |0.11     |0     |4.27      |
|tasks_count          |1        |16384      |130.47   |10    |812.71    |
|node_count           |1        |2048       |36.19    |4     |161.97    |
|energy_consumed      |-13759549|12082701255|796824.87|0     |48978522.1|
