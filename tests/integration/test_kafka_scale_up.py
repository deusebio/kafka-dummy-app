from typing import Optional
from uuid import uuid4

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


@pytest_asyncio.fixture
async def model() -> Model:
    current_model = Model()

    await current_model.connect_current()

    yield current_model

    await current_model.disconnect()


async def get_credentials(
    model: Model, app_name: str = "user"
) -> tuple[str, str, list]:
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
    bootstrap_server = kafka_data["endpoints"].split(",")

    return username, password, bootstrap_server


@pytest.mark.asyncio
async def test_juju_connection(model: Model):
    status = await model.get_status()

    assert "kafka" in status.applications


@pytest.mark.asyncio
async def test_non_replicated_topic_creation(model: Model):
    username, password, bootstrap_server = await get_credentials(model, "user")

    client = KafkaClient(servers=bootstrap_server, username=username, password=password)

    topic_name = uuid4().hex

    topic_config = NewTopic(
        name=topic_name,
        num_partitions=4,
        replication_factor=1,
    )

    client.create_topic(topic=topic_config)


@pytest.mark.asyncio
async def test_replicated_topic_creation_ko(model: Model):
    username, password, bootstrap_server = await get_credentials(model, "user")

    client = KafkaClient(servers=bootstrap_server, username=username, password=password)

    topic_name = uuid4().hex

    topic_config = NewTopic(
        name=topic_name,
        num_partitions=4,
        replication_factor=3,
    )

    with pytest.raises(InvalidReplicationFactorError):
        client.create_topic(topic=topic_config)


@pytest.mark.asyncio
async def test_replicated_topic_creation_ok(model: Model):

    kafka: Application = model.applications["kafka"]
    await kafka.add_unit(2)

    # Scaling up the Kafka cluster
    await model.wait_for_idle(apps=["kafka"], status="active")

    username, password, bootstrap_server = await get_credentials(model, "user")

    client = KafkaClient(servers=bootstrap_server, username=username, password=password)

    topic_name = uuid4().hex

    topic_config = NewTopic(
        name=topic_name,
        num_partitions=4,
        replication_factor=3,
    )

    client.create_topic(topic=topic_config)
