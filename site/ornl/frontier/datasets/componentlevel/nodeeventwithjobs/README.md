# componentlevel/nodeeventwithjobs
This dataset is processed from crayextelemetry. It contains only node level sensors that are not
sampled at regular intervals, but instead emit events intermittently. It is not pivoted like the
other datasets and is in long format. Each record contains the allocation_id of the slurm job
running on the node at the time.

If you are looking for the regularly sampled node sensors such as power and temperature info, use
`componentlevel/nodetswithjobs` instead.

- Saved: `s3a://<your-bucket>/tier1/frontier/componentlevel/nodeeventwithjobs` as parquets
- Stream: `src-event-frontier-componentlevelnodeeventwithjobs` as Avro
- Size: 1 MiB/day

## Schema

- timestamp
    - Time of the event
    - type: TIMESTAMP
- xname
    - Unique identifier for the node of the measurement, e.g. x2509c4s4b1
    - type: STRING
- row
    - Row index of the node
    - type: BIGINT
- col
    - Col index of the node
    - type: BIGINT
- chassis
    - Chassis index of the node
    - type: BIGINT
- blade
    - Blade index of the node
    - type: BIGINT
- node
    - Node index on blade, 0 or 1
    - type: BIGINT
- sensor_id
    - Unique id for the sensor the event came from
    - type: STRING
- parental_context
    - type: STRING
- location_type
    - Type of location the sensor came from
    - type: STRING
- telemetry_source
    - type: STRING
- parental_index
    - type: BIGINT
- physical_context
    - type: STRING
- index
    - type: BIGINT
- physical_sub_context
    - type: STRING
- message_id
    - type: STRING
- device_specific_context
    - type: STRING
- value
    - type: DOUBLE
- allocation_id
    - Allocation Id of the job associated with this record
    - type: STRING
- job_time_start
    - Start time of the job associated with this record
    - type: TIMESTAMP

## Stats

|name          |min|max           |mean             |median   |stddev           |
|--------------|---|--------------|-----------------|---------|-----------------|
|row           |0  |5             |                 |         |                 |
|col           |0  |11            |                 |         |                 |
|chassis       |0  |7             |                 |         |                 |
|blade         |0  |7             |                 |         |                 |
|node          |0  |1             |                 |         |                 |
|parental_index|0  |1             |0.65             |1        |0.48             |
|index         |0  |1             |0.53             |1        |0.5              |
|value         |528|28786678349196|12172069636570.75|1416165.5|14189255172334.69|
