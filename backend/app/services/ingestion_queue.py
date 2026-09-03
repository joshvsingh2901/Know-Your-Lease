import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, PositiveInt

from app.core.config import settings


class IngestionQueueError(RuntimeError):
    """A safe application-level boundary for queue provider failures."""


class IngestionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    document_id: uuid.UUID
    ingestion_version: PositiveInt = 1


class IngestionQueue(ABC):
    @abstractmethod
    def enqueue(self, document_id: uuid.UUID, ingestion_version: int) -> None:
        """Publish an ingestion request containing only the document identifier."""


@dataclass(frozen=True)
class ReceivedIngestionMessage:
    body: str
    receipt_handle: str
    message_id: str | None = None


class IngestionQueueConsumer(ABC):
    @abstractmethod
    def receive(self) -> ReceivedIngestionMessage | None:
        """Long-poll for at most one ingestion message."""

    @abstractmethod
    def delete(self, receipt_handle: str) -> None:
        """Acknowledge a successfully processed message."""


class SQSIngestionQueue(IngestionQueue):
    def __init__(self, *, client: Any, queue_url: str) -> None:
        self.client = client
        self.queue_url = queue_url

    def enqueue(self, document_id: uuid.UUID, ingestion_version: int) -> None:
        body = IngestionMessage(
            document_id=document_id,
            ingestion_version=ingestion_version,
        ).model_dump_json()
        try:
            self.client.send_message(QueueUrl=self.queue_url, MessageBody=body)
        except (BotoCoreError, ClientError) as exc:
            raise IngestionQueueError("The ingestion request could not be queued.") from exc


class SQSIngestionQueueConsumer(IngestionQueueConsumer):
    def __init__(self, *, client: Any, queue_url: str) -> None:
        self.client = client
        self.queue_url = queue_url

    def receive(self) -> ReceivedIngestionMessage | None:
        try:
            response = self.client.receive_message(
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
            )
        except (BotoCoreError, ClientError) as exc:
            raise IngestionQueueError("The ingestion queue could not be polled.") from exc

        messages = response.get("Messages", [])
        if not messages:
            return None

        message = messages[0]
        body = message.get("Body")
        receipt_handle = message.get("ReceiptHandle")
        message_id = message.get("MessageId")
        if not isinstance(body, str) or not isinstance(receipt_handle, str):
            raise IngestionQueueError("The ingestion queue returned an invalid response.")
        return ReceivedIngestionMessage(
            body=body,
            receipt_handle=receipt_handle,
            message_id=message_id if isinstance(message_id, str) else None,
        )

    def delete(self, receipt_handle: str) -> None:
        try:
            self.client.delete_message(
                QueueUrl=self.queue_url,
                ReceiptHandle=receipt_handle,
            )
        except (BotoCoreError, ClientError) as exc:
            raise IngestionQueueError("The ingestion message could not be acknowledged.") from exc


def _sqs_client() -> Any:
    return boto3.client("sqs", region_name=settings.aws_region)


@lru_cache(maxsize=1)
def get_ingestion_queue() -> IngestionQueue | None:
    if settings.ingestion_mode != "sqs":
        return None
    return SQSIngestionQueue(
        client=_sqs_client(),
        queue_url=settings.sqs_ingestion_queue_url or "",
    )


@lru_cache(maxsize=1)
def get_ingestion_queue_consumer() -> IngestionQueueConsumer:
    if settings.ingestion_mode != "sqs":
        raise RuntimeError("The ingestion worker requires INGESTION_MODE=sqs.")
    return SQSIngestionQueueConsumer(
        client=_sqs_client(),
        queue_url=settings.sqs_ingestion_queue_url or "",
    )
