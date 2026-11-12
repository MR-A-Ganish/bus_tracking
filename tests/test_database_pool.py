"""Pool ownership must follow the worker process, including preloaded apps."""
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import database


class WorkerPoolTests(unittest.TestCase):
    def test_a_new_worker_creates_its_own_pool(self):
        with patch.object(database,"_pool",None), patch.object(database,"_pool_pid",None):
            with patch("database.ConnectionPool") as factory, patch("database.os.getpid") as pid:
                with patch("database.atexit.register"):
                    pid.return_value=100
                    database._open_connection()
                    database._open_connection()
                    self.assertEqual(factory.call_count,1)
                    pid.return_value=101
                    database._open_connection()
                    self.assertEqual(factory.call_count,2)
                    self.assertEqual(database._pool_pid,101)


if __name__ == "__main__":
    unittest.main()
