import argparse
import logging
import signal
import threading
import time
from collections.abc import Callable

from pydantic import ValidationError

from app.core.config import settings, validate_worker_runtime_settings
from app.services.document_ingestion import (
    DocumentIngestionService,
    IngestionOutcome,
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


class IngestionWorker:
    def __init__(
        self,
        *,
        consumer: IngestionQueueConsumer,
        ingestion_service: DocumentIngestionService,
        queue_error_delay_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.consumer = consumer
        self.ingestion_service = ingestion_service
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
            outcome = self.ingestion_service.process_document(
                message.document_id,
                message.ingestion_version,
            )
        except Exception:
            logger.exception(
                "Unexpected ingestion failure for document %s; message was not acknowledged",
                message.document_id,
            )
            return

        if not isinstance(outcome, IngestionOutcome):
            logger.error(
                "Ingestion service returned an invalid outcome for document %s",
                message.document_id,
            )
            return

        if not outcome.acknowledge:
            logger.warning(
                "Ingestion outcome=%s for document %s version=%d; message was not "
                "acknowledged",
                outcome.value,
                message.document_id,
                message.ingestion_version,
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
        logger.info(
            "Acknowledged ingestion message for document %s version=%d outcome=%s",
            message.document_id,
            message.ingestion_version,
            outcome.value,
        )


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
    validate_worker_runtime_settings(settings)
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
