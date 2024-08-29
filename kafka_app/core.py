#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""KafkaClient class library for basic client connections to a Kafka Charm cluster.

`KafkaClient` provides an interface from which to make generic client connections
to a running Kafka Charm cluster. This can be as an administrator, producer or consumer,
provided that the necessary ACLs and user credentials have already been created.

Example usage for charms using `KafkaClient`:

For a produer application
```python

    client = KafkaClient(
        servers=bootstrap_servers,
        username=username,
        password=password,
        security_protocol="SASL_PLAINTEXT",  # SASL_SSL for TLS enabled Kafka clusters
    )

    # if topic has not yet been created
    if "admin" in roles:
        topic_config = NewTopic(
            name=topic,
            num_partitions=5,
            replication_factor=len(num_brokers)-1
        )

        logger.info(f"Creating new topic - {topic}")
        client.create_topic(topic=topic_config)

    logger.info("Producer - Starting...")
    for message in SOME_ITERABLE:
        client.produce_message(topic_name=topic, message_content=message)
```

Or, for a consumer application
```python
    client = KafkaClient(
        servers=bootstrap_servers,
        username=username,
        password=password,
        security_protocol="SASL_PLAINTEXT",  # SASL_SSL for TLS enabled Kafka clusters
    )

    logger.info("Consumer - Starting...")
    client.subscribe_to_topic(topic_name=topic, consumer_group_prefix=consumer_group_prefix)
    for message in client.messages():
        logger.info(message)
```
"""
from __future__ import annotations

import logging
from functools import cached_property
from typing import Generator, List, Optional

from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer
from kafka.admin import NewTopic

logger = logging.getLogger(__name__)


class KafkaClient:
    """Simplistic KafkaClient built on top of kafka-python."""

    API_VERSION = (2, 5, 0)

    def __init__(
        self,
        servers: List[str],
        username: Optional[str],
        password: Optional[str],
        cafile_path: Optional[str] = None,
        replication_factor: int = 3,
    ) -> None:
        self.servers = servers
        self.username = username
        self.password = password
        self.cafile_path = cafile_path
        self.replication_factor = replication_factor

        self.security_protocol = "SASL_SSL" if cafile_path else "SASL_PLAINTEXT"

        self._subscription: Optional[str] = None
        self._consumer_group_prefix: Optional[str] = None

    @cached_property
    def _admin_client(self) -> KafkaAdminClient:
        """Initialises and caches a `KafkaAdminClient`."""
        return KafkaAdminClient(
            client_id=self.username,
            bootstrap_servers=self.servers,
            ssl_check_hostname=False,
            security_protocol=self.security_protocol,
            sasl_plain_username=self.username,
            sasl_plain_password=self.password,
            sasl_mechanism="SCRAM-SHA-512",
            ssl_cafile=self.cafile_path,
        )

    @cached_property
    def _producer_client(self) -> KafkaProducer:
        """Initialises and caches a `KafkaProducer`."""
        return KafkaProducer(
            bootstrap_servers=self.servers,
            ssl_check_hostname=False,
            security_protocol=self.security_protocol,
            sasl_plain_username=self.username,
            sasl_plain_password=self.password,
            sasl_mechanism="SCRAM-SHA-512",
            ssl_cafile=self.cafile_path,
            acks="all",
            retries=10,
            retry_backoff_ms=1000,
        )

    @cached_property
    def _consumer_client(self) -> KafkaConsumer:
        """Initialises and caches a `KafkaConsumer`."""
        return KafkaConsumer(
            bootstrap_servers=self.servers,
            ssl_check_hostname=False,
            security_protocol=self.security_protocol,
            sasl_plain_username=self.username,
            sasl_plain_password=self.password,
            sasl_mechanism="SCRAM-SHA-512",
            ssl_cafile=self.cafile_path,
            group_id=self._consumer_group_prefix,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            consumer_timeout_ms=15000,
        )

    def create_topic(self, topic: NewTopic) -> None:
        """Creates a new topic on the Kafka cluster.

        Requires `KafkaClient` username to have `TOPIC CREATE` ACL permissions
            for desired topic.

        Args:
            topic: the configuration of the topic to create
        """
        self._admin_client.create_topics(new_topics=[topic], validate_only=False)

    def delete_topics(self, topics: list[str]) -> None:
        """Deletes a topic.

        Args:
            topics: list of topics to delete
        """
        self._admin_client.delete_topics(topics=topics)

    def subscribe_to_topic(
        self, topic_name: str, consumer_group_prefix: Optional[str] = None
    ) -> None:
        """Subscribes client to a specific topic, called when wishing to run a Consumer client.

        Requires `KafkaClient` username to have `TOPIC READ` ACL permissions
            for desired topic.
        Optionally requires `KafkaClient` username to have `GROUP READ` ACL permissions
            for desired consumer-group id.

        Args:
            topic_name: the topic to subscribe to
            consumer_group_prefix: (optional) the consumer group_id prefix to join
        """
        self._consumer_group_prefix = (
            consumer_group_prefix + "1" if consumer_group_prefix else None
        )
        self._subscription = topic_name
        self._consumer_client.subscribe(topics=[topic_name])

    def messages(self) -> Generator:
        """Iterable of consumer messages.

        Returns:
            Generator of messages

        Raises:
            AttributeError: if topic not yet subscribed to
        """
        if not self._subscription:
            msg = "Client not yet subscribed to a topic, cannot provide messages"
            logger.error(msg)
            raise AttributeError(msg)

        yield from self._consumer_client

    def produce_message(
        self, topic_name: str, message_content: bytes, timeout: int = 30
    ) -> None:
        """Sends message to target topic on the cluster.

        Requires `KafkaClient` username to have `TOPIC WRITE` ACL permissions
            for desired topic.

        Args:
            topic_name: the topic to send messages to
            message_content: the content of the message to send
            timeout: timeout for blocking after sending the message, defaults to 30s

        Raises:
            KafkaTimeoutError, KafkaError (general)
        """
        future = self._producer_client.send(topic_name, message_content)
        future.get(timeout=timeout)
        logger.debug(
            f"Message published to topic={topic_name}, message content: {message_content.decode('utf-8')}"
        )

    def close(self) -> None:
        """Close the connection to the client."""
        self._admin_client.close()
        self._producer_client.close()
        self._consumer_client.close()
