import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from handlers.callback_handler import is_owner_cb, register_callback_handlers
from handlers.queue_manager import QueueManager, VideoTask
from handlers.video_handler import is_owner, register_video_handlers


class TestBotFilters(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        config.OWNER_ID = 987654321

    async def test_owner_filter_allows_owner(self):
        msg = MagicMock()
        msg.from_user.id = 987654321
        self.assertTrue(await is_owner(None, None, msg))

    async def test_owner_filter_blocks_strangers(self):
        msg = MagicMock()
        msg.from_user.id = 111222333
        self.assertFalse(await is_owner(None, None, msg))

    async def test_owner_filter_handles_no_user(self):
        msg = MagicMock()
        msg.from_user = None
        self.assertFalse(await is_owner(None, None, msg))

    async def test_callback_owner_filter(self):
        query = MagicMock()
        query.from_user.id = 987654321
        self.assertTrue(await is_owner_cb(None, None, query))

        query.from_user.id = 999999999
        self.assertFalse(await is_owner_cb(None, None, query))


class TestQueueManager(unittest.IsolatedAsyncioTestCase):
    async def test_queue_add_and_callback(self):
        qm = QueueManager()
        client = AsyncMock()
        qm.start(client)

        msg = AsyncMock()
        msg.chat.id = 12345
        msg.id = 100
        msg.reply_text = AsyncMock()
        status_msg = AsyncMock()
        status_msg.chat.id = 12345
        status_msg.id = 101
        msg.reply_text.return_value = status_msg

        # Mock the worker processing method so it doesn't try to download from TG
        with patch.object(qm, "_process_task", new_callable=AsyncMock) as mock_process:
            task = await qm.add_task(
                message=msg,
                file_id="abc123file",
                file_name="sample.mp4",
                file_size=1024 * 1024,
            )

            self.assertIsNotNone(task)
            self.assertEqual(qm.get_task(task.task_id), task)

            # Test callback resolution
            self.assertFalse(task.choice_future.done())
            handled = qm.handle_callback_choice(task.task_id, 720)
            self.assertTrue(handled)
            self.assertTrue(task.choice_future.done())
            self.assertEqual(task.choice_future.result(), 720)

        # Cancel worker loop
        if qm._worker_task:
            qm._worker_task.cancel()


class TestHandlerRegistration(unittest.TestCase):
    def test_registration(self):
        app = MagicMock()
        register_video_handlers(app)
        register_callback_handlers(app)
        # Verify handlers were registered via decorators
        self.assertGreater(app.on_message.call_count, 0)
        self.assertGreater(app.on_callback_query.call_count, 0)


if __name__ == "__main__":
    unittest.main()
