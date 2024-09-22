from typing import Optional
from uuid import uuid4
from dataclasses import dataclass

import pytest
import pytest_asyncio
from juju.action import Action
from juju.application import Application
from juju.model import Model
from juju.unit import Unit
from kafka.admin import NewTopic
from kafka.errors import InvalidReplicationFactorError
from numpy.distutils.system_info import NotFoundError

from kafka_app.main import KafkaClient


@dataclass
class KafkaCredentials:
    username: str
    password: str
    bootstrap_servers: list[str]


@pytest_asyncio.fixture
async def model() -> Model:
    current_model = Model()

    await current_model.connect_current()

    yield current_model

    await current_model.disconnect()


@pytest.fixture
def app_name():
    return "user"

@pytest_asyncio.fixture
async def kafka_credentials(
    model: Model, app_name: str,
) -> KafkaCredentials:
    user: Application = model.applications[app_name]

    leader: Optional[Unit] = None
    for unit in user.units:
        is_leader = await unit.is_leader_from_status()
        if is_leader:
            leader = unit
            break

    if leader is None:
        raise NotFoundError(f"application {app_name} does not have a leader")

    res: Action = await leader.run_action("get-credentials")
    await res.wait()

    kafka_data = res.results["kafka"]

    username = kafka_data["username"]
    password = kafka_data["password"]
    bootstrap_servers = kafka_data["endpoints"].split(",")

    return KafkaCredentials(
        username=username,
        password=password,
        bootstrap_servers=bootstrap_servers
    )


@pytest.mark.asyncio
async def test_juju_connection(model: Model):
    status = await model.get_status()

    assert "kafka" in status.applications


@pytest.mark.asyncio
async def test_non_replicated_topic_creation(kafka_credentials: KafkaCredentials):
    client = KafkaClient(
        servers=kafka_credentials.bootstrap_servers,
        username=kafka_credentials.username,
        password=kafka_credentials.password
    )

    topic_name = uuid4().hex

    topic_config = NewTopic(
        name=topic_name,
        num_partitions=4,
        replication_factor=1,
    )

    client.create_topic(topic=topic_config)


@pytest.mark.asyncio
async def test_replicated_topic_creation_ko(kafka_credentials: KafkaCredentials):
    client = KafkaClient(
        servers=kafka_credentials.bootstrap_servers,
        username=kafka_credentials.username,
        password=kafka_credentials.password
    )

    topic_name = uuid4().hex

    topic_config = NewTopic(
        name=topic_name,
        num_partitions=4,
        replication_factor=3,
    )

    with pytest.raises(InvalidReplicationFactorError):
        client.create_topic(topic=topic_config)


@pytest.mark.asyncio
async def test_replicated_topic_creation_ok(
        model: Model, kafka_credentials: KafkaCredentials
):

    kafka: Application = model.applications["kafka"]
    await kafka.add_unit(2)

    # Scaling up the Kafka cluster
    await model.wait_for_idle(apps=["kafka"], status="active")

    client = KafkaClient(
        servers=kafka_credentials.bootstrap_servers,
        username=kafka_credentials.username,
        password=kafka_credentials.password
    )

    topic_name = uuid4().hex

    topic_config = NewTopic(
        name=topic_name,
        num_partitions=4,
        replication_factor=3,
    )

    client.create_topic(topic=topic_config)
