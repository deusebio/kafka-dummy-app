# Kafka Dummy App 

This is a simple app to show the usage of the [Setup Kafka GitHub Action](https://github.com/deusebio/setup-kafka-action).

The App provides a simple CLI tooling to produce and consumer messages from Kafka. When consuming messages, it is possible then store the information into a MongoDB database.

## Setup 

Install the Python package

```commandline
pip install . 
```

After this you should have access to the `kafka-app` CLI app. There are four entry points:

* `create-topic`
* `producer`
* `consumer`
* `report`

All the CLI also provide the following arguments to speficy the connection to the Kafka cluster:

| Parameter             | Default          |
|-----------------------|------------------|
| `--username`          | user             |
| `--password`          | password         |
| `--bootstrap-server`  | localhost:9092   |
| `--cafile-path`       | None             |

Below we provide more information on the custom specification for the single entry points. 

### Create a topic

```
create-topic <topic-name>
``` 

Use the `--replication-factor` and `--num-partition` arguments to customize these parameters during topic creation.

### Produce messages

```
producer <topic-name> <num_messages>` 
```

### Consume  messages

```
consumer <topic-name>
```

You can specify the consumer group via the `--consumer-group` argument. Use the `--mongo-uri` parameter to specify a sink for the consumed messages into a MongoDB database 

### Export Report

```
report <topic-name> <mongo_uri>
``` 

For exporting a report of the received messages in the MongoDB database. Use the `--fields` parameter to customize the export fields messages need to be aggregate against.



