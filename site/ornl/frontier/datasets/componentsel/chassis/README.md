# componentsel/chassis
This dataset is processed from componentlevel/chassists. It selects and renames a subset
of important chassis level sensors.

- Saved: `s3a://<your-bucket>/tier2/frontier/componentsel/chassis` as parquets
- Stream: `svc-ts-frontier-componentselchassis` as Avro
- Size: 64 MiB/day

## Schema

- timestamp
    - Time of the measurement, floored to 15 sec
    - type: TIMESTAMP
- xname
    - Unique identifier for the chassis of the measurement, e.g. x2007c7
    - type: STRING
- row
    - Row index of the chassis.
    - type: BIGINT
- col
    - Col index of the chassis
    - type: BIGINT
- chassis
    - Chassis index in cabinet
    - type: BIGINT
- rectifier0_input_power
    - Input power for Rectifier0 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- rectifier0_output_power
    - Output power for Rectifier0 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- rectifier1_input_power
    - Input power for Rectifier1 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- rectifier1_output_power
    - Output power for Rectifier1 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- rectifier2_input_power
    - Input power for Rectifier2 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- rectifier2_output_power
    - Output power for Rectifier2 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- rectifier3_input_power
    - Input power for Rectifier3 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- rectifier3_output_power
    - Output power for Rectifier3 (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec

## Stats

|name                   |min    |max    |mean   |median |stddev|
|-----------------------|-------|-------|-------|-------|------|
|row                    |0      |6      |2.64   |3      |1.82  |
|col                    |0      |11     |5.69   |6      |3.52  |
|chassis                |0      |7      |3.5    |3.5    |2.29  |
|rectifier0_input_power |1817   |6553   |2971.13|2952   |389.6 |
|rectifier0_output_power|1912.07|6902.53|2868.91|2844.53|371.77|
|rectifier1_input_power |1806   |6294   |2958.17|2927   |386.49|
|rectifier1_output_power|1728   |6702.9 |2854.11|2821.38|370.06|
|rectifier2_input_power |888    |6084   |2905.41|2897   |404.76|
|rectifier2_output_power|864.07 |6116.01|2804.65|2786.45|375.54|
|rectifier3_input_power |1129   |5671   |2890.33|2877   |372.42|
|rectifier3_output_power|1739.75|6101.32|2792.8 |2770.9 |344.09|
