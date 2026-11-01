# componentsel/chassis
This dataset is processed from componentlevel/nodetswithjobs. It selects and renames a
subset of important node level sensors. Each record contains the allocation_id of the
slurm job running on the node at the time.

- Saved: `s3a://<your-bucket>/tier2/frontier/componentsel/node` as parquets
- Stream: `svc-ts-frontier-componentselnode` as Avro
- Size: 1 GiB/day

## Schema

- timestamp
    - Time of the measurement, floored to 15 sec
    - type: TIMESTAMP
- xname
    - Unique identifier for the node of the measurement, e.g. x2509c4s4b1
    - type: STRING
- row
    - Row index of the node.
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
- allocation_id
    - Allocation Id of the job associated with this record
    - type: STRING
- job_time_start
    - Start time of the job associated with this record
    - type: TIMESTAMP
- node_power
    - Total node power usage (unit: W, interval: 2 sec)
    - type: DOUBLE
    - unit: W
    - interval: 2 sec
- node_temp
    - Max temperature seen on the node (unit: degC)
    - type: DOUBLE
    - unit: degC
- node_energy
    - Energy counter for node (unit: J, interval: 1 min)
    - type: DOUBLE
    - unit: J
    - interval: 1 min
- node_energy_delta
    - Energy consumed by node in this timestep (unit: J)
    - type: DOUBLE
    - unit: J
- cpu0_power
    - Power usage of CPU0 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- cpu0_temp
    - Temperature of CPU0 (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- cpu0_energy
    - Energy counter for CPU0 (unit: J, interval: 1 min)
    - type: DOUBLE
    - unit: J
    - interval: 1 min
- cpu0_energy_delta
    - Energy consumed by CPU0 in this timestep (unit: J)
    - type: DOUBLE
    - unit: J
- gpu0_power
    - Power usage of GPU0 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- gpu0_temp
    - Temperature of GPU0 (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- gpu0_energy
    - Energy counter for GPU0 (unit: J, interval: 1 min)
    - type: DOUBLE
    - unit: J
    - interval: 1 min
- gpu0_energy_delta
    - Energy consumed by GPU0 in this timestep (unit: J)
    - type: DOUBLE
    - unit: J
- gpu1_power
    - Power usage of GPU1 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- gpu1_temp
    - Temperature of GPU1 (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- gpu1_energy
    - Energy counter for GPU1 (unit: J, interval: 1 min)
    - type: DOUBLE
    - unit: J
    - interval: 1 min
- gpu1_energy_delta
    - Energy consumed by GPU1 in this timestep (unit: J)
    - type: DOUBLE
    - unit: J
- gpu2_power
    - Power usage of GPU2 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- gpu2_temp
    - Temperature of GPU2 (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- gpu2_energy
    - Energy counter for GPU2 (unit: J, interval: 1 min)
    - type: DOUBLE
    - unit: J
    - interval: 1 min
- gpu2_energy_delta
    - Energy consumed by GPU2 in this timestep (unit: J)
    - type: DOUBLE
    - unit: J
- gpu3_power
    - Power usage of GPU3 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- gpu3_temp
    - Temperature of GPU3 (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- gpu3_energy
    - Energy counter for GPU3 (unit: J, interval: 1 min)
    - type: DOUBLE
    - unit: J
    - interval: 1 min
- gpu3_energy_delta
    - Energy consumed by GPU3 in this timestep (unit: J)
    - type: DOUBLE
    - unit: J
- cpu_memory_power
    - Power usage of RAM (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- cpu_memory_energy
    - Energy counter for RAM (unit: J, interval: 1 min)
    - type: DOUBLE
    - unit: J
    - interval: 1 min
- cpu_memory_energy_delta
    - Energy consumed by RAM in this timestep (unit: J)
    - type: DOUBLE
    - unit: J

## Stats

|name                   |min    |max       |mean        |median     |stddev     |
|-----------------------|-------|----------|------------|-----------|-----------|
|row                    |0      |6         |            |           |           |
|col                    |0      |11        |            |           |           |
|chassis                |0      |7         |            |           |           |
|blade                  |0      |7         |            |           |           |
|node                   |0      |1         |            |           |           |
|node_power             |39     |64205     |636.21      |614.29     |205.09     |
|node_temp              |0      |80        |43.84       |43         |3.24       |
|node_energy            |4855090|1191424437|747931582.41|752540975  |78759324.88|
|node_energy_delta      |594.25 |65884     |9618.93     |9295       |2478.8     |
|cpu0_power             |18     |355       |35.43       |33         |13.43      |
|cpu0_temp              |32.62  |63.38     |40.46       |39.75      |2.98       |
|cpu0_energy            |1024655|222397805 |52507583.41 |53429215   |5802586.67 |
|cpu0_energy_delta      |133.75 |4785.75   |561.43      |509.25     |178.95     |
|gpu0_power             |48.06  |889.16    |100.95      |94.14      |41.98      |
|gpu0_temp              |0      |80        |42.46       |42         |3.29       |
|gpu0_energy            |2861868|177548944 |130653665.83|130983488  |15387186.2 |
|gpu0_energy_delta      |584    |10410.75  |1524.25     |1407.5     |552.38     |
|gpu1_power             |4.61   |818.3     |99.33       |92.83      |41.44      |
|gpu1_temp              |0      |68        |40.24       |40         |2.9        |
|gpu1_energy            |2712785|172702477 |129103023.94|129454941.5|15222561.19|
|gpu1_energy_delta      |583.5  |10799.33  |1500.74     |1383.25    |541.55     |
|gpu2_power             |26.99  |824.23    |99.65       |92.83      |41.3       |
|gpu2_temp              |0      |78        |41.48       |41         |3.33       |
|gpu2_energy            |2769090|178383842 |129703440.85|130011356  |15326520.82|
|gpu2_energy_delta      |568.5  |11039.33  |1505.21     |1388.5     |543.84     |
|gpu3_power             |26.33  |824.89    |98.9        |92.17      |40.94      |
|gpu3_temp              |0      |67        |39.64       |40         |2.85       |
|gpu3_energy            |2806865|175116909 |128581226.08|128918352  |15189616.86|
|gpu3_energy_delta      |563    |10537     |1494.98     |1378.25    |536.89     |
|cpu_memory_power       |18     |355       |35.43       |33         |13.43      |
|cpu_memory_energy      |2007788|61966203  |55718823.32 |56329151   |4661497.4  |
|cpu_memory_energy_delta|271.25 |1743.25   |1016.95     |1004       |52.29      |
