# componentsel/cdu
This dataset is processed from componentlevel/cduts. It selects and renames a subset of important
CDU sensors.


- Saved: `s3a://<your-bucket>/tier2/frontier/componentsel/cdu` as parquets
- Stream: `svc-ts-frontier-componentselcdu` as Avro
- Size: 2 MiB/day

## Schema

- timestamp
    - Time of the measurement, floored to 15 sec
    - type: TIMESTAMP
- xname
    - Unique identifier for the CDU of the measurement, e.g. x2007c1. The CDU xname is the xname of the neighboring cabinet
    - type: STRING
- row
    - Row index of the cdu.
    - type: BIGINT
- col
    - Col index of the cdu. (Note this the col of the neighboring cabinet.)
    - type: BIGINT
- power
    - AC Input power to the CDU (unit: W, interval: 15 sec)
    - type: DOUBLE
    - unit: W
    - interval: 15 sec
- liquid_inlet_0_flow_primary
    - Liquid Inlet 0 Liquid Flow Primary, i.e. the facility supply flowrate (unit: gal/min, interval: 1 min)
    - type: DOUBLE
    - unit: gal/min
    - interval: 1 min
- liquid_inlet_0_temperature_primary
    - Liquid Inlet 0 Temperature Primary i.e. the facility supply temperature (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- liquid_outlet_0_temperature_primary
    - Liquid Outlet 0 Temperature Primary i.e. the facility return temperature (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- liquid_inlet_0_pressure_primary
    - Liquid Inlet_0 Pressure Primary i.e. the facility supply pressure (unit: lbs/in^2, interval: 1 min)
    - type: DOUBLE
    - unit: lbs/in^2
    - interval: 1 min
- liquid_outlet_0_pressure_primary
    - Liquid Outlet 0 Pressure Primary i.e. the facility return pressure (unit: lbs/in^2, interval: 1 min)
    - type: DOUBLE
    - unit: lbs/in^2
    - interval: 1 min
- liquid_outlet_0_flow_secondary
    - Liquid Outlet 0 Liquid Flow Secondary i.e. the rack supply flowrate (unit: gal/min, interval: 1 min)
    - type: DOUBLE
    - unit: gal/min
    - interval: 1 min
- liquid_inlet_1_temperature_secondary
    - Liquid Inlet 1 Temperature Secondary i.e. rack return temperature (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- liquid_outlet_1_temperature_secondary
    - Liquid Outlet 1 Temperature Secondary i.e. the rack supply temperature (unit: degC, interval: 1 min)
    - type: DOUBLE
    - unit: degC
    - interval: 1 min
- liquid_inlet_1_pressure_secondary
    - Liquid Inlet 1 Pressure Secondary i.e. the rack return pressure (unit: lbs/in^2, interval: 1 min)
    - type: DOUBLE
    - unit: lbs/in^2
    - interval: 1 min
- liquid_outlet_1_pressure_secondary
    - Liquid Outlet 1 Pressure Secondary i.e. the rack supply pressure (unit: lbs/in^2, interval: 1 min)
    - type: DOUBLE
    - unit: lbs/in^2
    - interval: 1 min
- pump_1_input_pressure_secondary
    - Pump 1 Input Pressure (unit: lbs/in^2, interval: 1 min)
    - type: DOUBLE
    - unit: lbs/in^2
    - interval: 1 min

## Stats

|name                                 |min |max |mean   |median|stddev |
|-------------------------------------|----|----|-------|------|-------|
|row                                  |0   |6   |       |      |       |
|col                                  |2   |9   |       |      |       |
|power                                |900 |9600|7996.53|9000  |2546.61|
|liquid_inlet_0_flow_primary          |18.3|74.7|53.02  |53.1  |8.46   |
|liquid_inlet_0_temperature_primary   |11.9|13.7|12.82  |12.8  |0.32   |
|liquid_outlet_0_temperature_primary  |29.9|34  |31.96  |32    |0.7    |
|liquid_inlet_0_pressure_primary      |61.3|63.3|62.2   |62.2  |0.34   |
|liquid_outlet_0_pressure_primary     |39.8|40.6|40.21  |40.2  |0.12   |
|liquid_outlet_0_flow_secondary       |172 |283 |264.97 |269   |19.11  |
|liquid_inlet_1_temperature_secondary |29.8|34.1|31.93  |31.9  |0.68   |
|liquid_outlet_1_temperature_secondary|25.5|30.4|27.98  |28    |0.75   |
|liquid_inlet_1_pressure_secondary    |19.1|25.8|22.98  |23.1  |1.65   |
|liquid_outlet_1_pressure_secondary   |46.7|53.2|50.48  |50.6  |1.64   |
|pump_1_input_pressure_secondary      |11  |17  |14.61  |14.9  |1.47   |
