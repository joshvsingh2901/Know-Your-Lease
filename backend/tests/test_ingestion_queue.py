import json
import uuid

import boto3
import pytest
from botocore.stub import Stubber

from app.services.ingestion_queue import (
    IngestionQueueError,
    SQSIngestionQueue,
    SQSIngestionQueueConsumer,
)

REGION = "ca-central-1"
QUEUE_URL = "https://sqs.ca-central-1.amazonaws.com/123456789012/ingestion"


@pytest.fixture()
def sqs_client():
    return boto3.client(
        "sqs",
        region_name=REGION,
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
        aws_session_token="test-session-token",
    )


def test_sqs_queue_serializes_versioned_document_identifier(sqs_client) -> None:
    document_id = uuid.uuid4()
    queue = SQSIngestionQueue(client=sqs_client, queue_url=QUEUE_URL)

    with Stubber(sqs_client) as stubber:
        stubber.add_response(
            "send_message",
            {"MessageId": "message-id", "MD5OfMessageBody": "0" * 32},
            {
                "QueueUrl": QUEUE_URL,
                "MessageBody": json.dumps(
                    {"version": 1, "document_id": str(document_id)},
                    separators=(",", ":"),
                ),
            },
        )
        queue.enqueue(document_id)


def test_sqs_send_failure_maps_to_safe_queue_error(sqs_client) -> None:
    document_id = uuid.uuid4()
    queue = SQSIngestionQueue(client=sqs_client, queue_url=QUEUE_URL)

    with Stubber(sqs_client) as stubber:
        stubber.add_client_error(
            "send_message",
            service_error_code="ServiceUnavailable",
            service_message="private provider detail and credential",
            http_status_code=503,
            expected_params={
                "QueueUrl": QUEUE_URL,
                "MessageBody": json.dumps(
                    {"version": 1, "document_id": str(document_id)},
                    separators=(",", ":"),
                ),
            },
        )

        with pytest.raises(IngestionQueueError) as exc_info:
            queue.enqueue(document_id)

    assert str(exc_info.value) == "The ingestion request could not be queued."
    assert "private provider detail" not in str(exc_info.value)


def test_sqs_consumer_long_polls_one_message_and_deletes_it(sqs_client) -> None:
    consumer = SQSIngestionQueueConsumer(client=sqs_client, queue_url=QUEUE_URL)
    body = json.dumps({"version": 1, "document_id": str(uuid.uuid4())})

    with Stubber(sqs_client) as stubber:
        stubber.add_response(
            "receive_message",
            {
                "Messages": [
                    {
                        "MessageId": "message-id",
                        "ReceiptHandle": "receipt-handle",
                        "Body": body,
                    }
                ]
            },
            {
                "QueueUrl": QUEUE_URL,
                "MaxNumberOfMessages": 1,
                "WaitTimeSeconds": 20,
            },
        )
        stubber.add_response(
            "delete_message",
            {},
            {"QueueUrl": QUEUE_URL, "ReceiptHandle": "receipt-handle"},
        )

        received = consumer.receive()
        assert received is not None
        assert received.body == body
        assert received.message_id == "message-id"
        consumer.delete(received.receipt_handle)
