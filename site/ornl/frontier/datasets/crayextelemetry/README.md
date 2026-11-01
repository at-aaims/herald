# crayextelemetry
This dataset is the source dataset for all power/energy metrics off frontier.
We are reading it from the Cadence kafka stream `stf002hpc.frontier.hpcm.crayex_telemetry`
Its in long format.

- Saved: `s3a://<your-bucket>/tier0/frontier/crayextelemetry/raw` as parquets
- Size: 58 GiB/day

## Schema
- Timestamp TIMESTAMP
- Location STRING
- TelemetrySource STRING
- ParentalContext STRING
- ParentalIndex INT
- PhysicalContext STRING
- Index INT
- PhysicalSubContext STRING
- MessageId STRING
- DeviceSpecificContext STRING
- Value DOUBLE

