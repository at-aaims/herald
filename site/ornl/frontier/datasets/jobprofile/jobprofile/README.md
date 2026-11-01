# jobprofile/jobprofile
This dataset is processed from componentsel/node. It collapses the data into a single timeseries
per job such that there will be one record per job per 15 seconds. Each record contains aggregated
statistics for all the nodes in the job.

- Saved: `s3a://<your-bucket>/tier2/frontier/jobprofile/jobprofile` as parquets
- Stream: `dev-svc-ts-frontier-jobprofile` as Avro
- Size: 64 MiB/day

## Schema

- allocation_id
    - Unique identifier for the job
    - type: STRING
- timestamp
    - Time of the measurement, floored to 15 sec
    - type: TIMESTAMP
- reporting_node_count
    - Number of nodes reporting metrics during the measurement. Note this can be different than the job node count, and can vary throughout a job if some nodes don't report telemetry reliably.
    - type: BIGINT
- min_node_power
    - Min of node_power across all nodes in the job
    - type: DOUBLE
- max_node_power
    - Max of node_power across all nodes in the job
    - type: DOUBLE
- mean_node_power
    - Mean of node_power across all nodes in the job
    - type: DOUBLE
- stddev_node_power
    - Population standard deviation of node_power across all nodes in the job
    - type: DOUBLE
- sum_node_power
    - Total node_power summed across all nodes in the job
    - type: DOUBLE
- quantile_25_node_power
    - 25th percentile of node_power across all nodes in the job
    - type: DOUBLE
- quantile_50_node_power
    - 50th percentile of node_power across all nodes in the job
    - type: DOUBLE
- quantile_75_node_power
    - 75th percentile of node_power across all nodes in the job
    - type: DOUBLE
- quantile_99_node_power
    - 99th percentile of node_power across all nodes in the job
    - type: DOUBLE
- min_cpu0_power
    - Min of cpu0_power across all nodes in the job
    - type: DOUBLE
- max_cpu0_power
    - Max of cpu0_power across all nodes in the job
    - type: DOUBLE
- mean_cpu0_power
    - Mean of cpu0_power across all nodes in the job
    - type: DOUBLE
- stddev_cpu0_power
    - Population standard deviation of cpu0_power across all nodes in the job
    - type: DOUBLE
- sum_cpu0_power
    - Total cpu0_power summed across all nodes in the job
    - type: DOUBLE
- quantile_25_cpu0_power
    - 25th percentile of cpu0_power across all nodes in the job
    - type: DOUBLE
- quantile_50_cpu0_power
    - 50th percentile of cpu0_power across all nodes in the job
    - type: DOUBLE
- quantile_75_cpu0_power
    - 75th percentile of cpu0_power across all nodes in the job
    - type: DOUBLE
- quantile_99_cpu0_power
    - 99th percentile of cpu0_power across all nodes in the job
    - type: DOUBLE
- min_cpu_memory_power
    - Min of cpu_memory_power across all nodes in the job
    - type: DOUBLE
- max_cpu_memory_power
    - Max of cpu_memory_power across all nodes in the job
    - type: DOUBLE
- mean_cpu_memory_power
    - Mean of cpu_memory_power across all nodes in the job
    - type: DOUBLE
- stddev_cpu_memory_power
    - Population standard deviation of cpu_memory_power across all nodes in the job
    - type: DOUBLE
- sum_cpu_memory_power
    - Total cpu_memory_power summed across all nodes in the job
    - type: DOUBLE
- quantile_25_cpu_memory_power
    - 25th percentile of cpu_memory_power across all nodes in the job
    - type: DOUBLE
- quantile_50_cpu_memory_power
    - 50th percentile of cpu_memory_power across all nodes in the job
    - type: DOUBLE
- quantile_75_cpu_memory_power
    - 75th percentile of cpu_memory_power across all nodes in the job
    - type: DOUBLE
- quantile_99_cpu_memory_power
    - 99th percentile of cpu_memory_power across all nodes in the job
    - type: DOUBLE
- min_gpu_power
    - Min of gpu_power across all nodes in the job
    - type: DOUBLE
- max_gpu_power
    - Max of gpu_power across all nodes in the job
    - type: DOUBLE
- mean_gpu_power
    - Mean of gpu_power across all nodes in the job
    - type: DOUBLE
- stddev_gpu_power
    - Population standard deviation of gpu_power across all nodes in the job
    - type: DOUBLE
- sum_gpu_power
    - Total gpu_power summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu_power
    - 25th percentile of gpu_power across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu_power
    - 50th percentile of gpu_power across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu_power
    - 75th percentile of gpu_power across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu_power
    - 99th percentile of gpu_power across all nodes in the job
    - type: DOUBLE
- min_gpu0_power
    - Min of gpu0_power across all nodes in the job
    - type: DOUBLE
- max_gpu0_power
    - Max of gpu0_power across all nodes in the job
    - type: DOUBLE
- mean_gpu0_power
    - Mean of gpu0_power across all nodes in the job
    - type: DOUBLE
- stddev_gpu0_power
    - Population standard deviation of gpu0_power across all nodes in the job
    - type: DOUBLE
- sum_gpu0_power
    - Total gpu0_power summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu0_power
    - 25th percentile of gpu0_power across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu0_power
    - 50th percentile of gpu0_power across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu0_power
    - 75th percentile of gpu0_power across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu0_power
    - 99th percentile of gpu0_power across all nodes in the job
    - type: DOUBLE
- min_gpu1_power
    - Min of gpu1_power across all nodes in the job
    - type: DOUBLE
- max_gpu1_power
    - Max of gpu1_power across all nodes in the job
    - type: DOUBLE
- mean_gpu1_power
    - Mean of gpu1_power across all nodes in the job
    - type: DOUBLE
- stddev_gpu1_power
    - Population standard deviation of gpu1_power across all nodes in the job
    - type: DOUBLE
- sum_gpu1_power
    - Total gpu1_power summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu1_power
    - 25th percentile of gpu1_power across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu1_power
    - 50th percentile of gpu1_power across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu1_power
    - 75th percentile of gpu1_power across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu1_power
    - 99th percentile of gpu1_power across all nodes in the job
    - type: DOUBLE
- min_gpu2_power
    - Min of gpu2_power across all nodes in the job
    - type: DOUBLE
- max_gpu2_power
    - Max of gpu2_power across all nodes in the job
    - type: DOUBLE
- mean_gpu2_power
    - Mean of gpu2_power across all nodes in the job
    - type: DOUBLE
- stddev_gpu2_power
    - Population standard deviation of gpu2_power across all nodes in the job
    - type: DOUBLE
- sum_gpu2_power
    - Total gpu2_power summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu2_power
    - 25th percentile of gpu2_power across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu2_power
    - 50th percentile of gpu2_power across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu2_power
    - 75th percentile of gpu2_power across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu2_power
    - 99th percentile of gpu2_power across all nodes in the job
    - type: DOUBLE
- min_gpu3_power
    - Min of gpu3_power across all nodes in the job
    - type: DOUBLE
- max_gpu3_power
    - Max of gpu3_power across all nodes in the job
    - type: DOUBLE
- mean_gpu3_power
    - Mean of gpu3_power across all nodes in the job
    - type: DOUBLE
- stddev_gpu3_power
    - Population standard deviation of gpu3_power across all nodes in the job
    - type: DOUBLE
- sum_gpu3_power
    - Total gpu3_power summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu3_power
    - 25th percentile of gpu3_power across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu3_power
    - 50th percentile of gpu3_power across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu3_power
    - 75th percentile of gpu3_power across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu3_power
    - 99th percentile of gpu3_power across all nodes in the job
    - type: DOUBLE
- min_node_temp
    - Min of node_temp across all nodes in the job
    - type: DOUBLE
- max_node_temp
    - Max of node_temp across all nodes in the job
    - type: DOUBLE
- mean_node_temp
    - Mean of node_temp across all nodes in the job
    - type: DOUBLE
- stddev_node_temp
    - Population standard deviation of node_temp across all nodes in the job
    - type: DOUBLE
- quantile_25_node_temp
    - 25th percentile of node_temp across all nodes in the job
    - type: DOUBLE
- quantile_50_node_temp
    - 50th percentile of node_temp across all nodes in the job
    - type: DOUBLE
- quantile_75_node_temp
    - 75th percentile of node_temp across all nodes in the job
    - type: DOUBLE
- quantile_99_node_temp
    - 99th percentile of node_temp across all nodes in the job
    - type: DOUBLE
- min_cpu0_temp
    - Min of cpu0_temp across all nodes in the job
    - type: DOUBLE
- max_cpu0_temp
    - Max of cpu0_temp across all nodes in the job
    - type: DOUBLE
- mean_cpu0_temp
    - Mean of cpu0_temp across all nodes in the job
    - type: DOUBLE
- stddev_cpu0_temp
    - Population standard deviation of cpu0_temp across all nodes in the job
    - type: DOUBLE
- quantile_25_cpu0_temp
    - 25th percentile of cpu0_temp across all nodes in the job
    - type: DOUBLE
- quantile_50_cpu0_temp
    - 50th percentile of cpu0_temp across all nodes in the job
    - type: DOUBLE
- quantile_75_cpu0_temp
    - 75th percentile of cpu0_temp across all nodes in the job
    - type: DOUBLE
- quantile_99_cpu0_temp
    - 99th percentile of cpu0_temp across all nodes in the job
    - type: DOUBLE
- min_gpu_temp
    - Min of gpu_temp across all nodes in the job
    - type: DOUBLE
- max_gpu_temp
    - Max of gpu_temp across all nodes in the job
    - type: DOUBLE
- mean_gpu_temp
    - Mean of gpu_temp across all nodes in the job
    - type: DOUBLE
- stddev_gpu_temp
    - Population standard deviation of gpu_temp across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu_temp
    - 25th percentile of gpu_temp across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu_temp
    - 50th percentile of gpu_temp across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu_temp
    - 75th percentile of gpu_temp across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu_temp
    - 99th percentile of gpu_temp across all nodes in the job
    - type: DOUBLE
- min_gpu0_temp
    - Min of gpu0_temp across all nodes in the job
    - type: DOUBLE
- max_gpu0_temp
    - Max of gpu0_temp across all nodes in the job
    - type: DOUBLE
- mean_gpu0_temp
    - Mean of gpu0_temp across all nodes in the job
    - type: DOUBLE
- stddev_gpu0_temp
    - Population standard deviation of gpu0_temp across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu0_temp
    - 25th percentile of gpu0_temp across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu0_temp
    - 50th percentile of gpu0_temp across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu0_temp
    - 75th percentile of gpu0_temp across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu0_temp
    - 99th percentile of gpu0_temp across all nodes in the job
    - type: DOUBLE
- min_gpu1_temp
    - Min of gpu1_temp across all nodes in the job
    - type: DOUBLE
- max_gpu1_temp
    - Max of gpu1_temp across all nodes in the job
    - type: DOUBLE
- mean_gpu1_temp
    - Mean of gpu1_temp across all nodes in the job
    - type: DOUBLE
- stddev_gpu1_temp
    - Population standard deviation of gpu1_temp across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu1_temp
    - 25th percentile of gpu1_temp across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu1_temp
    - 50th percentile of gpu1_temp across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu1_temp
    - 75th percentile of gpu1_temp across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu1_temp
    - 99th percentile of gpu1_temp across all nodes in the job
    - type: DOUBLE
- min_gpu2_temp
    - Min of gpu2_temp across all nodes in the job
    - type: DOUBLE
- max_gpu2_temp
    - Max of gpu2_temp across all nodes in the job
    - type: DOUBLE
- mean_gpu2_temp
    - Mean of gpu2_temp across all nodes in the job
    - type: DOUBLE
- stddev_gpu2_temp
    - Population standard deviation of gpu2_temp across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu2_temp
    - 25th percentile of gpu2_temp across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu2_temp
    - 50th percentile of gpu2_temp across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu2_temp
    - 75th percentile of gpu2_temp across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu2_temp
    - 99th percentile of gpu2_temp across all nodes in the job
    - type: DOUBLE
- min_gpu3_temp
    - Min of gpu3_temp across all nodes in the job
    - type: DOUBLE
- max_gpu3_temp
    - Max of gpu3_temp across all nodes in the job
    - type: DOUBLE
- mean_gpu3_temp
    - Mean of gpu3_temp across all nodes in the job
    - type: DOUBLE
- stddev_gpu3_temp
    - Population standard deviation of gpu3_temp across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu3_temp
    - 25th percentile of gpu3_temp across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu3_temp
    - 50th percentile of gpu3_temp across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu3_temp
    - 75th percentile of gpu3_temp across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu3_temp
    - 99th percentile of gpu3_temp across all nodes in the job
    - type: DOUBLE
- min_gpu_energy_delta
    - Min of gpu_energy_delta across all nodes in the job
    - type: DOUBLE
- max_gpu_energy_delta
    - Max of gpu_energy_delta across all nodes in the job
    - type: DOUBLE
- mean_gpu_energy_delta
    - Mean of gpu_energy_delta across all nodes in the job
    - type: DOUBLE
- stddev_gpu_energy_delta
    - Population standard deviation of gpu_energy_delta across all nodes in the job
    - type: DOUBLE
- sum_gpu_energy_delta
    - Total gpu_energy_delta summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu_energy_delta
    - 25th percentile of gpu_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu_energy_delta
    - 50th percentile of gpu_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu_energy_delta
    - 75th percentile of gpu_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu_energy_delta
    - 99th percentile of gpu_energy_delta across all nodes in the job
    - type: DOUBLE
- min_gpu0_energy_delta
    - Min of gpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- max_gpu0_energy_delta
    - Max of gpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- mean_gpu0_energy_delta
    - Mean of gpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- stddev_gpu0_energy_delta
    - Population standard deviation of gpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- sum_gpu0_energy_delta
    - Total gpu0_energy_delta summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu0_energy_delta
    - 25th percentile of gpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu0_energy_delta
    - 50th percentile of gpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu0_energy_delta
    - 75th percentile of gpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu0_energy_delta
    - 99th percentile of gpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- min_gpu1_energy_delta
    - Min of gpu1_energy_delta across all nodes in the job
    - type: DOUBLE
- max_gpu1_energy_delta
    - Max of gpu1_energy_delta across all nodes in the job
    - type: DOUBLE
- mean_gpu1_energy_delta
    - Mean of gpu1_energy_delta across all nodes in the job
    - type: DOUBLE
- stddev_gpu1_energy_delta
    - Population standard deviation of gpu1_energy_delta across all nodes in the job
    - type: DOUBLE
- sum_gpu1_energy_delta
    - Total gpu1_energy_delta summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu1_energy_delta
    - 25th percentile of gpu1_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu1_energy_delta
    - 50th percentile of gpu1_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu1_energy_delta
    - 75th percentile of gpu1_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu1_energy_delta
    - 99th percentile of gpu1_energy_delta across all nodes in the job
    - type: DOUBLE
- min_gpu2_energy_delta
    - Min of gpu2_energy_delta across all nodes in the job
    - type: DOUBLE
- max_gpu2_energy_delta
    - Max of gpu2_energy_delta across all nodes in the job
    - type: DOUBLE
- mean_gpu2_energy_delta
    - Mean of gpu2_energy_delta across all nodes in the job
    - type: DOUBLE
- stddev_gpu2_energy_delta
    - Population standard deviation of gpu2_energy_delta across all nodes in the job
    - type: DOUBLE
- sum_gpu2_energy_delta
    - Total gpu2_energy_delta summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu2_energy_delta
    - 25th percentile of gpu2_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu2_energy_delta
    - 50th percentile of gpu2_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu2_energy_delta
    - 75th percentile of gpu2_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu2_energy_delta
    - 99th percentile of gpu2_energy_delta across all nodes in the job
    - type: DOUBLE
- min_gpu3_energy_delta
    - Min of gpu3_energy_delta across all nodes in the job
    - type: DOUBLE
- max_gpu3_energy_delta
    - Max of gpu3_energy_delta across all nodes in the job
    - type: DOUBLE
- mean_gpu3_energy_delta
    - Mean of gpu3_energy_delta across all nodes in the job
    - type: DOUBLE
- stddev_gpu3_energy_delta
    - Population standard deviation of gpu3_energy_delta across all nodes in the job
    - type: DOUBLE
- sum_gpu3_energy_delta
    - Total gpu3_energy_delta summed across all nodes in the job
    - type: DOUBLE
- quantile_25_gpu3_energy_delta
    - 25th percentile of gpu3_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_50_gpu3_energy_delta
    - 50th percentile of gpu3_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_75_gpu3_energy_delta
    - 75th percentile of gpu3_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_99_gpu3_energy_delta
    - 99th percentile of gpu3_energy_delta across all nodes in the job
    - type: DOUBLE
- min_cpu0_energy_delta
    - Min of cpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- max_cpu0_energy_delta
    - Max of cpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- mean_cpu0_energy_delta
    - Mean of cpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- stddev_cpu0_energy_delta
    - Population standard deviation of cpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- sum_cpu0_energy_delta
    - Total cpu0_energy_delta summed across all nodes in the job
    - type: DOUBLE
- quantile_25_cpu0_energy_delta
    - 25th percentile of cpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_50_cpu0_energy_delta
    - 50th percentile of cpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_75_cpu0_energy_delta
    - 75th percentile of cpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_99_cpu0_energy_delta
    - 99th percentile of cpu0_energy_delta across all nodes in the job
    - type: DOUBLE
- min_cpu_memory_energy_delta
    - Min of cpu_memory_energy_delta across all nodes in the job
    - type: DOUBLE
- max_cpu_memory_energy_delta
    - Max of cpu_memory_energy_delta across all nodes in the job
    - type: DOUBLE
- mean_cpu_memory_energy_delta
    - Mean of cpu_memory_energy_delta across all nodes in the job
    - type: DOUBLE
- stddev_cpu_memory_energy_delta
    - Population standard deviation of cpu_memory_energy_delta across all nodes in the job
    - type: DOUBLE
- sum_cpu_memory_energy_delta
    - Total cpu_memory_energy_delta summed across all nodes in the job
    - type: DOUBLE
- quantile_25_cpu_memory_energy_delta
    - 25th percentile of cpu_memory_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_50_cpu_memory_energy_delta
    - 50th percentile of cpu_memory_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_75_cpu_memory_energy_delta
    - 75th percentile of cpu_memory_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_99_cpu_memory_energy_delta
    - 99th percentile of cpu_memory_energy_delta across all nodes in the job
    - type: DOUBLE
- min_node_energy_delta
    - Min of node_energy_delta across all nodes in the job
    - type: DOUBLE
- max_node_energy_delta
    - Max of node_energy_delta across all nodes in the job
    - type: DOUBLE
- mean_node_energy_delta
    - Mean of node_energy_delta across all nodes in the job
    - type: DOUBLE
- stddev_node_energy_delta
    - Population standard deviation of node_energy_delta across all nodes in the job
    - type: DOUBLE
- sum_node_energy_delta
    - Total node_energy_delta summed across all nodes in the job
    - type: DOUBLE
- quantile_25_node_energy_delta
    - 25th percentile of node_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_50_node_energy_delta
    - 50th percentile of node_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_75_node_energy_delta
    - 75th percentile of node_energy_delta across all nodes in the job
    - type: DOUBLE
- quantile_99_node_energy_delta
    - 99th percentile of node_energy_delta across all nodes in the job
    - type: DOUBLE
- date
    - type: DATE

## Stats

|name                               |min   |max        |mean      |median  |stddev     |
|-----------------------------------|------|-----------|----------|--------|-----------|
|reporting_node_count               |1     |8998       |215.51    |5       |1340.72    |
|min_node_power                     |39    |3049.71    |1369.21   |1158.38 |730.86     |
|max_node_power                     |608.14|64205      |1564.7    |1232.73 |2021.2     |
|mean_node_power                    |593.32|3049.71    |1419.83   |1175.18 |716.62     |
|stddev_node_power                  |0     |673.85     |21.51     |12.85   |41.09      |
|sum_node_power                     |608.14|6043099.95 |136634.55 |5803.68 |816722.36  |
|quantile_25_node_power             |577.71|3049.71    |1407.3    |1166.27 |713.65     |
|quantile_50_node_power             |597.25|3049.71    |1419.55   |1174.6  |717.61     |
|quantile_75_node_power             |604.14|3049.71    |1430.17   |1184.8  |718.67     |
|quantile_99_node_power             |608.14|3053.86    |1453.59   |1200.67 |721.98     |
|min_cpu0_power                     |18    |304        |77.16     |73      |30.2       |
|max_cpu0_power                     |25    |355        |91.86     |86      |34.45      |
|mean_cpu0_power                    |25    |304        |82.14     |79.25   |27.83      |
|stddev_cpu0_power                  |0     |64.32      |3.23      |2.23    |5.31       |
|sum_cpu0_power                     |25    |646139     |7780.66   |382     |46613.16   |
|quantile_25_cpu0_power             |25    |304        |79.78     |77      |28.91      |
|quantile_50_cpu0_power             |25    |304        |81.68     |79      |28.14      |
|quantile_75_cpu0_power             |25    |304        |84.25     |81      |27.76      |
|quantile_99_cpu0_power             |25    |304        |87.84     |86      |27.83      |
|min_cpu_memory_power               |18    |304        |77.16     |73      |30.2       |
|max_cpu_memory_power               |25    |355        |91.86     |86      |34.45      |
|mean_cpu_memory_power              |25    |304        |82.14     |79.25   |27.83      |
|stddev_cpu_memory_power            |0     |64.32      |3.23      |2.23    |5.31       |
|sum_cpu_memory_power               |25    |646139     |7780.66   |382     |46613.16   |
|quantile_25_cpu_memory_power       |25    |304        |79.78     |77      |28.91      |
|quantile_50_cpu_memory_power       |25    |304        |81.68     |79      |28.14      |
|quantile_75_cpu_memory_power       |25    |304        |84.25     |81      |27.76      |
|quantile_99_cpu_memory_power       |25    |304        |87.84     |86      |27.83      |
|min_gpu_power                      |7.24  |624.1      |159.16    |99.41   |110.08     |
|max_gpu_power                      |87.56 |889.16     |390.34    |424.95  |246.07     |
|mean_gpu_power                     |84.6  |692.76     |261.52    |198.97  |168.37     |
|stddev_gpu_power                   |0.28  |292.14     |75.87     |47.32   |75.05      |
|sum_gpu_power                      |338.38|3585966.91 |86416.85  |2998.1  |510004.66  |
|quantile_25_gpu_power              |64.52 |693.84     |189.57    |107.89  |126.73     |
|quantile_50_gpu_power              |82.95 |740.35     |242.97    |132.32  |175.92     |
|quantile_75_gpu_power              |85.58 |766.39     |299.95    |180.38  |217.28     |
|quantile_99_gpu_power              |87.56 |889.16     |386.71    |405.52  |246.23     |
|min_gpu0_power                     |48.06 |759.05     |209.35    |108.82  |166        |
|max_gpu0_power                     |82.95 |889.16     |332.61    |257.08  |235.52     |
|mean_gpu0_power                    |82.95 |759.05     |265.1     |176.29  |184.62     |
|stddev_gpu0_power                  |0     |324.28     |42.39     |5.92    |71.32      |
|sum_gpu0_power                     |82.95 |904395.52  |21876.19  |667.55  |129112.53  |
|quantile_25_gpu0_power             |82.95 |759.05     |234.89    |124.63  |178.73     |
|quantile_50_gpu0_power             |82.95 |763.6      |260.36    |133.64  |196.15     |
|quantile_75_gpu0_power             |82.95 |791.5      |290.91    |146.81  |215.63     |
|quantile_99_gpu0_power             |82.95 |889.16     |332.48    |257.08  |235.64     |
|min_gpu1_power                     |7.24  |728.11     |203.24    |108.82  |161.36     |
|max_gpu1_power                     |64.52 |818.3      |328.35    |256.09  |231.46     |
|mean_gpu1_power                    |64.52 |737.32     |259.4     |179.51  |179.62     |
|stddev_gpu1_power                  |0     |291.81     |43.1      |6.19    |71.43      |
|sum_gpu1_power                     |64.52 |894775.54  |21520.6   |671.17  |126957.39  |
|quantile_25_gpu1_power             |64.52 |732.72     |228.15    |124.1   |173.27     |
|quantile_50_gpu1_power             |64.52 |752.44     |254.56    |133.64  |191.2      |
|quantile_75_gpu1_power             |64.52 |773.83     |285.43    |146.81  |211.55     |
|quantile_99_gpu1_power             |64.52 |818.3      |328.22    |256.09  |231.57     |
|min_gpu2_power                     |26.99 |744.57     |207.89    |107.31  |162.36     |
|max_gpu2_power                     |81.63 |824.23     |330.12    |262.02  |232.36     |
|mean_gpu2_power                    |81.63 |766.76     |261.99    |177.17  |181.54     |
|stddev_gpu2_power                  |0     |297.83     |41.54     |6.25    |68.58      |
|sum_gpu2_power                     |81.63 |902485.96  |21590.52  |664.55  |127419.03  |
|quantile_25_gpu2_power             |80.97 |758.95     |231.84    |124.63  |174.22     |
|quantile_50_gpu2_power             |80.97 |766.39     |257.23    |133.64  |191.84     |
|quantile_75_gpu2_power             |81.63 |786.05     |286.3     |146.15  |210.92     |
|quantile_99_gpu2_power             |81.63 |824.23     |329.65    |262.02  |232.78     |
|min_gpu3_power                     |26.33 |724.82     |204.17    |105.1   |161.31     |
|max_gpu3_power                     |75.71 |824.89     |328.78    |258.72  |233.3      |
|mean_gpu3_power                    |75.71 |745.68     |259.58    |171.14  |180.32     |
|stddev_gpu3_power                  |0     |286.98     |42.5      |5.88    |70.91      |
|sum_gpu3_power                     |75.71 |890206.35  |21429.55  |650.43  |126518.12  |
|quantile_25_gpu3_power             |75.71 |759.88     |228.5     |123.11  |172.84     |
|quantile_50_gpu3_power             |75.71 |769.18     |255.14    |132.98  |191.31     |
|quantile_75_gpu3_power             |75.71 |782.2      |285.27    |144.83  |211.34     |
|quantile_99_gpu3_power             |75.71 |824.89     |328.26    |258.72  |233.75     |
|min_node_temp                      |0     |74         |53.68     |49.5    |9.42       |
|max_node_temp                      |41    |78         |57.57     |54.5    |9.11       |
|mean_node_temp                     |41    |74.6       |55.41     |50.8    |9.08       |
|stddev_node_temp                   |0     |6.93       |1.09      |1       |1.12       |
|quantile_25_node_temp              |40    |74         |54.62     |50      |9.15       |
|quantile_50_node_temp              |41    |74         |55.23     |50.75   |9.05       |
|quantile_75_node_temp              |41    |77         |56.07     |52      |9.22       |
|quantile_99_node_temp              |41    |78         |57.47     |54      |9.18       |
|min_cpu0_temp                      |35    |63.38      |49.27     |48.38   |6.23       |
|max_cpu0_temp                      |38.12 |63.38      |51.99     |51.25   |5.58       |
|mean_cpu0_temp                     |38.09 |63.38      |50.35     |49.25   |5.75       |
|stddev_cpu0_temp                   |0     |5.18       |0.7       |0.6     |0.82       |
|quantile_25_cpu0_temp              |37.5  |63.38      |49.83     |48.75   |5.93       |
|quantile_50_cpu0_temp              |38    |63.38      |50.24     |49.12   |5.82       |
|quantile_75_cpu0_temp              |38.12 |63.38      |50.72     |49.5    |5.66       |
|quantile_99_cpu0_temp              |38.12 |63.38      |51.83     |51.12   |5.71       |
|min_gpu_temp                       |0     |62         |42.91     |42      |12.56      |
|max_gpu_temp                       |40    |78         |56.1      |52      |10.38      |
|mean_gpu_temp                      |38.25 |67.75      |50.01     |46.4    |8.95       |
|stddev_gpu_temp                    |0.43  |12.05      |3.35      |2.95    |1.47       |
|quantile_25_gpu_temp               |32    |62         |46.65     |44      |7.59       |
|quantile_50_gpu_temp               |38    |66         |49.08     |46      |8.41       |
|quantile_75_gpu_temp               |38    |74         |52.02     |48      |9.92       |
|quantile_99_gpu_temp               |40    |78         |55.88     |52      |10.44      |
|min_gpu0_temp                      |0     |74         |49.69     |47      |13.22      |
|max_gpu0_temp                      |38    |76         |55.33     |52      |10.43      |
|mean_gpu0_temp                     |38    |74         |52.87     |49      |10.52      |
|stddev_gpu0_temp                   |0     |14.43      |1.33      |1.3     |1.35       |
|quantile_25_gpu0_temp              |38    |74         |52.02     |48      |10.71      |
|quantile_50_gpu0_temp              |38    |74         |52.7      |48      |10.62      |
|quantile_75_gpu0_temp              |38    |76         |53.68     |50      |10.62      |
|quantile_99_gpu0_temp              |38    |76         |55.24     |52      |10.48      |
|min_gpu1_temp                      |0     |68         |44.44     |43      |13.1       |
|max_gpu1_temp                      |32    |68         |50.5      |50      |7.7        |
|mean_gpu1_temp                     |32    |68         |48.03     |45      |7.97       |
|stddev_gpu1_temp                   |0     |11.4       |1.32      |1.33    |1.54       |
|quantile_25_gpu1_temp              |32    |68         |47.19     |44      |8.26       |
|quantile_50_gpu1_temp              |32    |68         |47.83     |44      |8.05       |
|quantile_75_gpu1_temp              |32    |68         |48.64     |46      |7.84       |
|quantile_99_gpu1_temp              |32    |68         |50.39     |49      |7.74       |
|min_gpu2_temp                      |0     |73         |48.93     |46      |13.04      |
|max_gpu2_temp                      |38    |78         |54.15     |50      |10.21      |
|mean_gpu2_temp                     |38    |74         |51.84     |47.99   |10.33      |
|stddev_gpu2_temp                   |0     |11.84      |1.21      |1.36    |1.21       |
|quantile_25_gpu2_temp              |38    |73         |51.01     |47      |10.48      |
|quantile_50_gpu2_temp              |38    |74         |51.75     |48      |10.39      |
|quantile_75_gpu2_temp              |38    |77         |52.56     |49      |10.34      |
|quantile_99_gpu2_temp              |38    |78         |54.06     |50      |10.26      |
|min_gpu3_temp                      |0     |64         |44.66     |43      |10.53      |
|max_gpu3_temp                      |32    |67         |49.43     |48      |7.44       |
|mean_gpu3_temp                     |32    |64         |47.28     |44.2    |7.56       |
|stddev_gpu3_temp                   |0     |11.13      |1.11      |1.17    |1.16       |
|quantile_25_gpu3_temp              |32    |64         |46.46     |44      |7.85       |
|quantile_50_gpu3_temp              |32    |64         |47.16     |44      |7.64       |
|quantile_75_gpu3_temp              |32    |64         |47.99     |45      |7.54       |
|quantile_99_gpu3_temp              |32    |67         |49.33     |47      |7.46       |
|min_gpu_energy_delta               |0     |8181.25    |3650.98   |2956.75 |2270.7     |
|max_gpu_energy_delta               |0     |11039.33   |4216.49   |3278.5  |2472.06    |
|mean_gpu_energy_delta              |0     |8641.9     |3934.58   |3110.27 |2363.15    |
|stddev_gpu_energy_delta            |0     |2921.34    |150.18    |95.29   |189.69     |
|sum_gpu_energy_delta               |0     |50428816.92|1248904.66|51739.62|7372128.77 |
|quantile_25_gpu_energy_delta       |0     |8452.25    |3803.86   |3028.5  |2320.48    |
|quantile_50_gpu_energy_delta       |0     |8539.75    |3913.13   |3093    |2366.73    |
|quantile_75_gpu_energy_delta       |0     |8698.5     |4017.27   |3158.88 |2400.94    |
|quantile_99_gpu_energy_delta       |0     |11039.33   |4200.76   |3277.38 |2481.26    |
|min_gpu0_energy_delta              |0     |8551.75    |3733.82   |2996    |2414.15    |
|max_gpu0_energy_delta              |0     |10410.75   |4035.93   |3170    |2463.72    |
|mean_gpu0_energy_delta             |0     |8888.31    |3887.11   |3086.75 |2428.76    |
|stddev_gpu0_energy_delta           |0     |2147.36    |86.01     |64.37   |151.14     |
|sum_gpu0_energy_delta              |0     |12785340.92|315986.65 |12232.88|1865115.04 |
|quantile_25_gpu0_energy_delta      |0     |8577       |3830.62   |3041    |2417.49    |
|quantile_50_gpu0_energy_delta      |0     |8679.75    |3877.95   |3082.5  |2432.11    |
|quantile_75_gpu0_energy_delta      |0     |8854.5     |3933.33   |3118    |2438.01    |
|quantile_99_gpu0_energy_delta      |0     |10410.75   |4030.07   |3170    |2468.83    |
|min_gpu1_energy_delta              |0     |8398.25    |3685.62   |3011.25 |2344.86    |
|max_gpu1_energy_delta              |0     |10799.33   |3995.69   |3192.25 |2394.29    |
|mean_gpu1_energy_delta             |0     |8864.86    |3844.98   |3105.03 |2361.21    |
|stddev_gpu1_energy_delta           |0     |2311.18    |86.85     |54.56   |158.82     |
|sum_gpu1_energy_delta              |0     |12551491.25|311021.65 |12314.38|1835637.6  |
|quantile_25_gpu1_energy_delta      |0     |8399.25    |3788.47   |3050    |2350.74    |
|quantile_50_gpu1_energy_delta      |0     |8528.25    |3833.59   |3088.12 |2365.33    |
|quantile_75_gpu1_energy_delta      |0     |10799.33   |3890.31   |3134.5  |2375.03    |
|quantile_99_gpu1_energy_delta      |0     |10799.33   |3989.82   |3192.25 |2399.6     |
|min_gpu2_energy_delta              |0     |8654       |3726.45   |2995.75 |2398.11    |
|max_gpu2_energy_delta              |0     |11039.33   |4016.19   |3185.5  |2446.22    |
|mean_gpu2_energy_delta             |0     |9091.02    |3863.04   |3085.9  |2418.69    |
|stddev_gpu2_energy_delta           |0     |2235.78    |83.57     |61.21   |153.04     |
|sum_gpu2_energy_delta              |0     |12594523.42|311972.28 |12173.5 |1841526.97 |
|quantile_25_gpu2_energy_delta      |0     |8654       |3804.97   |3034.38 |2410.39    |
|quantile_50_gpu2_energy_delta      |0     |8706       |3851.12   |3078.75 |2422.26    |
|quantile_75_gpu2_energy_delta      |0     |8909       |3903.8    |3118    |2425.59    |
|quantile_99_gpu2_energy_delta      |0     |11039.33   |4008.44   |3185.5  |2453.15    |
|min_gpu3_energy_delta              |0     |8414       |3686.79   |3018.38 |2327.16    |
|max_gpu3_energy_delta              |0     |10537      |4008.12   |3179.88 |2440.91    |
|mean_gpu3_energy_delta             |0     |8914.12    |3847.07   |3106.5  |2395.04    |
|stddev_gpu3_energy_delta           |0     |2259.15    |96.02     |63.55   |163.89     |
|sum_gpu3_energy_delta              |0     |12536463.5 |309924.09 |12388   |1829878.41 |
|quantile_25_gpu3_energy_delta      |0     |8521.25    |3784.56   |3051.25 |2377.1     |
|quantile_50_gpu3_energy_delta      |0     |8648.75    |3839.1    |3091    |2408.34    |
|quantile_75_gpu3_energy_delta      |0     |8711.5     |3897.79   |3131.88 |2418.11    |
|quantile_99_gpu3_energy_delta      |0     |10537      |3999.92   |3179.88 |2448.21    |
|min_cpu0_energy_delta              |0     |2647       |1199.79   |1183.75 |439.87     |
|max_cpu0_energy_delta              |0     |4785.75    |1339.19   |1268.5  |520.97     |
|mean_cpu0_energy_delta             |0     |2647       |1234.01   |1221.09 |424.72     |
|stddev_cpu0_energy_delta           |0     |909.22     |24.19     |13.05   |63.22      |
|sum_cpu0_energy_delta              |0     |8365330.83 |117772.29 |4889.88 |703477.74  |
|quantile_25_cpu0_energy_delta      |0     |2647       |1215.29   |1198.88 |433.59     |
|quantile_50_cpu0_energy_delta      |0     |2647       |1228.49   |1219.75 |429.38     |
|quantile_75_cpu0_energy_delta      |0     |2647       |1250.61   |1232.25 |426.82     |
|quantile_99_cpu0_energy_delta      |0     |2647       |1276.98   |1263.38 |422.75     |
|min_cpu_memory_energy_delta        |0     |1743.25    |1194.47   |1220.75 |211.16     |
|max_cpu_memory_energy_delta        |0     |1743.25    |1249.85   |1252.75 |208.53     |
|mean_cpu_memory_energy_delta       |0     |1743.25    |1215.72   |1232.5  |208.4      |
|stddev_cpu_memory_energy_delta     |0     |212.67     |15.53     |12.88   |22.77      |
|sum_cpu_memory_energy_delta        |0     |9234235.5  |210083.3  |5920    |1295192.39 |
|quantile_25_cpu_memory_energy_delta|0     |1743.25    |1203.98   |1225    |209.76     |
|quantile_50_cpu_memory_energy_delta|0     |1743.25    |1212.37   |1229.75 |209.39     |
|quantile_75_cpu_memory_energy_delta|0     |1743.25    |1223.44   |1236.5  |208.84     |
|quantile_99_cpu_memory_energy_delta|0     |1743.25    |1244.64   |1249.75 |209.82     |
|min_node_energy_delta              |0     |42670.75   |20089.39  |17554.75|11125.53   |
|max_node_energy_delta              |0     |65884      |21690.52  |18125.25|10966.44   |
|mean_node_energy_delta             |0     |42913.33   |20873.64  |17751.52|10943.7    |
|stddev_node_energy_delta           |0     |8336.73    |343.95    |186.65  |676.68     |
|sum_node_energy_delta              |0     |84308079.75|1976291.18|70732.88|11812450.82|
|quantile_25_node_energy_delta      |0     |42670.75   |20640.32  |17619.75|10885.79   |
|quantile_50_node_energy_delta      |0     |42949.25   |20862.27  |17719.5 |10956.47   |
|quantile_75_node_energy_delta      |0     |43350.25   |21057.19  |17816   |10980.67   |
|quantile_99_node_energy_delta      |0     |43701.5    |21427.66  |18019.75|11061.37   |
