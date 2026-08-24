from __future__ import annotations

import asyncio
import logging
import unittest

from viatradetgbot.app import wait_for_consumer_shutdown


class ConsumerShutdownTests(unittest.IsolatedAsyncioTestCase):
	async def test_propagates_timeout_raised_by_worker(self) -> None:
		async def fail_with_timeout() -> None:
			raise TimeoutError

		worker_task = asyncio.create_task(fail_with_timeout())

		try:
			await wait_for_consumer_shutdown(
				worker_task,
				grace_seconds=1,
				logger=logging.getLogger(__name__),
			)
		except TimeoutError:
			return

		self.fail("Worker TimeoutError must not be mistaken for the shutdown deadline.")

	async def test_waits_for_in_flight_message_before_cancelling_worker(self) -> None:
		stop_requested = asyncio.Event()
		worker_started = asyncio.Event()
		worker_finished = asyncio.Event()

		async def process_in_flight_message() -> None:
			worker_started.set()
			await stop_requested.wait()
			await asyncio.sleep(0)
			worker_finished.set()

		worker_task = asyncio.create_task(process_in_flight_message())
		await worker_started.wait()
		stop_requested.set()

		await wait_for_consumer_shutdown(
			worker_task,
			grace_seconds=1,
			logger=logging.getLogger(__name__),
		)

		self.assertTrue(worker_finished.is_set())
		self.assertFalse(worker_task.cancelled())
