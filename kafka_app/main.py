import logging

from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError
import os

import time

import pandas as pd

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from kafka_app.core import KafkaClient
import typer

import uuid

app = typer.Typer()
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

process_id = os.urandom(15).hex()

@app.command()
def producer(
    topic_name: str,
    num_messages: int,
    username: str = "user", password: str = "password",
    bootstrap_server: str = "localhost:9092",
    cafile_path: str | None = None,
):
    client = KafkaClient(
        servers=bootstrap_server.split(","),
        username=username,
        password=password,
        cafile_path=cafile_path
    )

    topic_config = NewTopic(
        name=topic_name,
        num_partitions=5, replication_factor=1
    )

    logger.info(f"Creating new topic - {topic_name}")

    try:
        client.create_topic(topic=topic_config)
    except TopicAlreadyExistsError:
        logger.info(f"Topic {topic_name} already exists")

    logger.info("Producer - Starting...")
    for ith in range(num_messages):
        logger.info(f"Process {process_id} producing message with seq number {ith}")
        message = f"{process_id}-{ith}"
        client.produce_message(
            topic_name=topic_name, message_content=message.encode("utf-8")
        )
        time.sleep(1.0)

@app.command()
def consumer(
    topic_name: str, consumer_group: str = "cg",
    username: str = "user", password: str = "password",
    bootstrap_server: str = "localhost:9092",
    cafile_path: str | None = None,
    mongo_uri: str | None = None
):
    client = KafkaClient(
        servers=bootstrap_server.split(","),
        username=username,
        password=password,
        cafile_path=cafile_path
    )

    if mongo_uri:
        mongo_client = MongoClient(mongo_uri)
        collection = mongo_client[topic_name].get_collection("consumer")
    else:
        collection = None

    logger.info("Consumer - Starting...")
    client.subscribe_to_topic(topic_name=topic_name,
                              consumer_group_prefix=consumer_group)

    for message in client.messages():
        logger.info(message)
        content = message.value.decode("utf-8")
        origin_id, sequence_number = content.split("-")
        content = {"_id": uuid.uuid4().hex, "content": content,
                   "origin_id": origin_id, "sequence_number": sequence_number,
                   "destination": process_id, "consumer_group": consumer_group}
        if collection is not None:
            try:
                collection.insert_one(content)
            except DuplicateKeyError:
                logger.error(f"Duplicated key with id: {content['_id']}")


@app.command()
def report(
    topic_name: str, mongo_uri: str, fields: str = "destination",
    output: str | None = None
):
    fields_lst = [field.strip() for field in fields.split(",")]

    keys = {name: f"${name}" for name in fields_lst}

    mongo_client = MongoClient(mongo_uri)
    collection = mongo_client[topic_name].get_collection("consumer")

    items = collection.aggregate([
        {"$group": {"_id": keys, "count": {"$sum": 1}}}
    ])

    df = pd.DataFrame([
        item["_id"] | {key: item[key] for key in item if key != "_id"}
        for item in items
    ]).set_index(fields_lst)

    if output:
        df.to_csv(output)

if __name__ == "__main__":
    app()
