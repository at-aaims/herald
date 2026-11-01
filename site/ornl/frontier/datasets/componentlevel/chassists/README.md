# componentlevel/chasssists
This dataset is processed from crayextelemetry. It contains the crayextelemetry
chassis level sensors in wide format.

- Saved: `s3a://<your-bucket>/tier1/frontier/componentlevel/chassists` as parquets
- Stream: `src-event-frontier-componentlevelchassists` as Avro
- Size: 170 MiB/day

##  Schema

- timestamp
    - Time of the measurement
    - type: TIMESTAMP
- xname
    - Unique identifier for the chassis of the measurement, e.g. x2509c4
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
- chassis_rectifier_0_input_power
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 15 sec
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 0
    - physical_sub_context: Input
    - message_id: Power
    - device_specific_context: None
- chassis_rectifier_0_output_power
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 15 sec
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 0
    - physical_sub_context: Output
    - message_id: Power
    - device_specific_context: None
- chassis_rectifier_1_input_power
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 15 sec
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 1
    - physical_sub_context: Input
    - message_id: Power
    - device_specific_context: None
- chassis_rectifier_1_output_power
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 15 sec
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 1
    - physical_sub_context: Output
    - message_id: Power
    - device_specific_context: None
- chassis_rectifier_2_input_power
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 15 sec
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 2
    - physical_sub_context: Input
    - message_id: Power
    - device_specific_context: None
- chassis_rectifier_2_output_power
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 15 sec
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 2
    - physical_sub_context: Output
    - message_id: Power
    - device_specific_context: None
- chassis_rectifier_3_input_power
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 15 sec
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 3
    - physical_sub_context: Input
    - message_id: Power
    - device_specific_context: None
- chassis_rectifier_3_output_power
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 15 sec
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 3
    - physical_sub_context: Output
    - message_id: Power
    - device_specific_context: None
- chassis_chassis_0_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Chassis
    - index: 0
    - physical_sub_context: None
    - message_id: Voltage
    - device_specific_context: None
- chassis_chassis_1_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Chassis
    - index: 1
    - physical_sub_context: None
    - message_id: Voltage
    - device_specific_context: None
- chassis_chassis_2_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Chassis
    - index: 2
    - physical_sub_context: None
    - message_id: Voltage
    - device_specific_context: None
- chassis_chassis_liquidinlet_0_input_pressure
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: Chassis
    - parental_index: None
    - physical_context: LiquidInlet
    - index: 0
    - physical_sub_context: Input
    - message_id: Pressure
    - device_specific_context: None
- chassis_chassis_liquidinlet_0_input_temperature
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: Chassis
    - parental_index: None
    - physical_context: LiquidInlet
    - index: 0
    - physical_sub_context: Input
    - message_id: Temperature
    - device_specific_context: None
- chassis_chassis_liquidoutlet_0_output_pressure
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: Chassis
    - parental_index: None
    - physical_context: LiquidOutlet
    - index: 0
    - physical_sub_context: Output
    - message_id: Pressure
    - device_specific_context: None
- chassis_chassis_liquidoutlet_0_output_temperature
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: Chassis
    - parental_index: None
    - physical_context: LiquidOutlet
    - index: 0
    - physical_sub_context: Output
    - message_id: Temperature
    - device_specific_context: None
- chassis_chassis_system_pressure_secondary
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: Chassis
    - parental_index: None
    - physical_context: System
    - index: None
    - physical_sub_context: None
    - message_id: Pressure
    - device_specific_context: Secondary
- chassis_chassis_voltageregulator_0_output_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: Chassis
    - parental_index: None
    - physical_context: VoltageRegulator
    - index: 0
    - physical_sub_context: Output
    - message_id: Voltage
    - device_specific_context: None
- chassis_chassis_voltageregulator_1_output_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: Chassis
    - parental_index: None
    - physical_context: VoltageRegulator
    - index: 1
    - physical_sub_context: Output
    - message_id: Voltage
    - device_specific_context: None
- chassis_chassis_voltageregulator_2_output_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: Chassis
    - parental_index: None
    - physical_context: VoltageRegulator
    - index: 2
    - physical_sub_context: Output
    - message_id: Voltage
    - device_specific_context: None
- chassis_rectifier_0_input_current_line3
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 0
    - physical_sub_context: Input
    - message_id: Current
    - device_specific_context: Line3
- chassis_rectifier_0_input_voltage_line3toline1
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 0
    - physical_sub_context: Input
    - message_id: Voltage
    - device_specific_context: Line3ToLine1
- chassis_rectifier_0_output_current
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 0
    - physical_sub_context: Output
    - message_id: Current
    - device_specific_context: None
- chassis_rectifier_0_output_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 0
    - physical_sub_context: Output
    - message_id: Voltage
    - device_specific_context: None
- chassis_rectifier_0_temperature
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 0
    - physical_sub_context: None
    - message_id: Temperature
    - device_specific_context: None
- chassis_rectifier_1_input_current_line3
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 1
    - physical_sub_context: Input
    - message_id: Current
    - device_specific_context: Line3
- chassis_rectifier_1_input_voltage_line3toline1
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 1
    - physical_sub_context: Input
    - message_id: Voltage
    - device_specific_context: Line3ToLine1
- chassis_rectifier_1_output_current
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 1
    - physical_sub_context: Output
    - message_id: Current
    - device_specific_context: None
- chassis_rectifier_1_output_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 1
    - physical_sub_context: Output
    - message_id: Voltage
    - device_specific_context: None
- chassis_rectifier_1_temperature
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 1
    - physical_sub_context: None
    - message_id: Temperature
    - device_specific_context: None
- chassis_rectifier_2_input_current_line3
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 2
    - physical_sub_context: Input
    - message_id: Current
    - device_specific_context: Line3
- chassis_rectifier_2_input_voltage_line3toline1
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 2
    - physical_sub_context: Input
    - message_id: Voltage
    - device_specific_context: Line3ToLine1
- chassis_rectifier_2_output_current
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 2
    - physical_sub_context: Output
    - message_id: Current
    - device_specific_context: None
- chassis_rectifier_2_output_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 2
    - physical_sub_context: Output
    - message_id: Voltage
    - device_specific_context: None
- chassis_rectifier_2_temperature
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 2
    - physical_sub_context: None
    - message_id: Temperature
    - device_specific_context: None
- chassis_rectifier_3_input_current_line3
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 3
    - physical_sub_context: Input
    - message_id: Current
    - device_specific_context: Line3
- chassis_rectifier_3_input_voltage_line3toline1
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 3
    - physical_sub_context: Input
    - message_id: Voltage
    - device_specific_context: Line3ToLine1
- chassis_rectifier_3_output_current
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 3
    - physical_sub_context: Output
    - message_id: Current
    - device_specific_context: None
- chassis_rectifier_3_output_voltage
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 3
    - physical_sub_context: Output
    - message_id: Voltage
    - device_specific_context: None
- chassis_rectifier_3_temperature
    - type: DOUBLE
    - location_type: chassis
    - telemetry_source: cC
    - interval: 1 min
    - parental_context: None
    - parental_index: None
    - physical_context: Rectifier
    - index: 3
    - physical_sub_context: None
    - message_id: Temperature
    - device_specific_context: None

## Stats

|name                                             |min    |max    |mean   |median |stddev|
|-------------------------------------------------|-------|-------|-------|-------|------|
|row                                              |0      |6      |       |       |      |
|col                                              |0      |11     |       |       |      |
|chassis                                          |0      |7      |       |       |      |
|chassis_rectifier_0_input_power                  |1817   |6553   |2971.17|2952   |389.52|
|chassis_rectifier_0_output_power                 |1912.07|6902.53|2868.91|2844.53|371.78|
|chassis_rectifier_1_input_power                  |1806   |6294   |2958.09|2927   |386.37|
|chassis_rectifier_1_output_power                 |1728   |6702.9 |2854.09|2821.38|370   |
|chassis_rectifier_2_input_power                  |888    |6084   |2905.39|2898   |404.76|
|chassis_rectifier_2_output_power                 |864.07 |6116.01|2804.6 |2786.45|375.3 |
|chassis_rectifier_3_input_power                  |1129   |5671   |2890.23|2877   |372.26|
|chassis_rectifier_3_output_power                 |1739.75|6101.32|2792.74|2770.9 |343.94|
|chassis_chassis_0_voltage                        |2.03   |2.05   |2.04   |2.04   |0.01  |
|chassis_chassis_1_voltage                        |2.03   |2.05   |2.04   |2.04   |0     |
|chassis_chassis_2_voltage                        |2.03   |2.86   |2.05   |2.04   |0.09  |
|chassis_chassis_liquidinlet_0_input_pressure     |45.72  |53.82  |50.31  |50.61  |1.63  |
|chassis_chassis_liquidinlet_0_input_temperature  |25.91  |31.43  |28.8   |28.83  |0.8   |
|chassis_chassis_liquidoutlet_0_output_pressure   |16.68  |30.92  |23.52  |23.59  |1.78  |
|chassis_chassis_liquidoutlet_0_output_temperature|30.38  |35.08  |32.66  |32.66  |0.71  |
|chassis_chassis_system_pressure_secondary        |38.63  |48.85  |44.01  |44.12  |1.78  |
|chassis_chassis_voltageregulator_0_output_voltage|23.46  |24.01  |23.64  |23.64  |0.1   |
|chassis_chassis_voltageregulator_1_output_voltage|3.3    |3.36   |3.33   |3.33   |0.01  |
|chassis_chassis_voltageregulator_2_output_voltage|5.19   |5.28   |5.24   |5.24   |0.02  |
|chassis_rectifier_0_input_current_line3          |2.25   |7.3    |3.65   |3.62   |0.47  |
|chassis_rectifier_0_input_voltage_line3toline1   |481.35 |496.92 |490.86 |492.32 |4.41  |
|chassis_rectifier_0_output_current               |4.97   |17.92  |7.48   |7.42   |0.97  |
|chassis_rectifier_0_output_voltage               |380.83 |383.98 |383.28 |383.3  |0.24  |
|chassis_rectifier_0_temperature                  |31     |37     |33.79  |34     |0.86  |
|chassis_rectifier_1_input_current_line3          |2.25   |7.67   |3.63   |3.6    |0.46  |
|chassis_rectifier_1_input_voltage_line3toline1   |481.25 |496.77 |490.84 |492.32 |4.45  |
|chassis_rectifier_1_output_current               |4.52   |17.3   |7.45   |7.36   |0.98  |
|chassis_rectifier_1_output_voltage               |381.05 |384    |383.29 |383.31 |0.24  |
|chassis_rectifier_1_temperature                  |31     |37     |33.75  |34     |0.85  |
|chassis_rectifier_2_input_current_line3          |1.23   |6.77   |3.57   |3.55   |0.49  |
|chassis_rectifier_2_input_voltage_line3toline1   |476    |496.82 |490.75 |492.27 |4.5   |
|chassis_rectifier_2_output_current               |2.25   |15.98  |7.32   |7.27   |0.98  |
|chassis_rectifier_2_output_voltage               |381.28 |384.14 |383.32 |383.33 |0.24  |
|chassis_rectifier_2_temperature                  |31     |37     |33.79  |34     |0.89  |
|chassis_rectifier_3_input_current_line3          |1.48   |6.84   |3.55   |3.54   |0.45  |
|chassis_rectifier_3_input_voltage_line3toline1   |476.15 |496.92 |490.72 |492.17 |4.46  |
|chassis_rectifier_3_output_current               |4.56   |15.42  |7.29   |7.23   |0.9   |
|chassis_rectifier_3_output_voltage               |381.06 |384.03 |383.33 |383.34 |0.22  |
|chassis_rectifier_3_temperature                  |31     |38     |33.82  |34     |0.87  |
