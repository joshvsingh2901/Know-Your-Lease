import argparse
import logging
import signal
import threading
import time
from collections.abc import Callable

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings, validate_runtime_settings
from app.core.database import SessionLocal
from app.models.document import Document
from app.services.document_ingestion import (
    DocumentIngestionService,
    get_ingestion_service,
)
from app.services.ingestion_queue import (
    IngestionMessage,
    IngestionQueueConsumer,
    IngestionQueueError,
    ReceivedIngestionMessage,
    get_ingestion_queue_consumer,
)

logger = logging.getLogger(__name__)
SessionFactory = Callable[[], Session]


class IngestionWorker:
    def __init__(
        self,
        *,
        consumer: IngestionQueueConsumer,
        ingestion_service: DocumentIngestionService,
        session_factory: SessionFactory = SessionLocal,
        queue_error_delay_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.consumer = consumer
        self.ingestion_service = ingestion_service
        self.session_factory = session_factory
        self.queue_error_delay_seconds = queue_error_delay_seconds
        self.sleep = sleep

    def run_once(self) -> None:
        try:
            received = self.consumer.receive()
        except IngestionQueueError:
            logger.exception("Could not poll the ingestion queue; retrying after a delay")
            self.sleep(self.queue_error_delay_seconds)
            return

        if received is None:
            return
        self._process_message(received)

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stop = stop_event or threading.Event()
        logger.info("Ingestion worker started")
        while not stop.is_set():
            self.run_once()
        logger.info("Ingestion worker stopped")

    def _process_message(self, received: ReceivedIngestionMessage) -> None:
        try:
            message = IngestionMessage.model_validate_json(received.body)
        except ValidationError:
            logger.warning(
                "Ignoring malformed ingestion message %s without acknowledging it",
                received.message_id or "<unknown>",
            )
            return

        try:
            with self.session_factory() as db:
                document_exists = db.get(Document, message.document_id) is not None
        except Exception:
            logger.exception(
                "Could not load document %s; message was not acknowledged",
                message.document_id,
            )
            return

        if not document_exists:
            logger.warning(
                "Document %s does not exist; message was not acknowledged",
                message.document_id,
            )
            return

        try:
            succeeded = self.ingestion_service.process_document(message.document_id)
        except Exception:
            logger.exception(
                "Unexpected ingestion failure for document %s; message was not acknowledged",
                message.document_id,
            )
            return

        if not succeeded:
            logger.warning(
                "Ingestion failed for document %s; message was not acknowledged",
                message.document_id,
            )
            return

        try:
            self.consumer.delete(received.receipt_handle)
        except IngestionQueueError:
            logger.exception(
                "Document %s completed but its queue message could not be acknowledged",
                message.document_id,
            )
            return
        logger.info("Acknowledged ingestion message for document %s", message.document_id)


def create_worker() -> IngestionWorker:
    return IngestionWorker(
        consumer=get_ingestion_queue_consumer(),
        ingestion_service=get_ingestion_service(),
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Know Your Lease ingestion worker")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate worker configuration without contacting SQS or providers.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    arguments = _arguments()
    validate_runtime_settings(settings)
    if settings.ingestion_mode != "sqs":
        raise SystemExit("The ingestion worker requires INGESTION_MODE=sqs.")
    if arguments.check:
        logger.info("Ingestion worker configuration is valid")
        return

    stop_event = threading.Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        logger.info("Received signal %s; stopping after the current poll", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    create_worker().run_forever(stop_event)


if __name__ == "__main__":
    main()
