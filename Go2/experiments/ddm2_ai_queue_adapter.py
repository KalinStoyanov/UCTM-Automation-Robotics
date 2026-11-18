"""Offline adapter to an existing DD-M2 CommandQueue.

No WebRTC connection and no worker creation.
"""


class QueueExecutor:
    def __init__(self, queue):
        self.queue = queue

    def __call__(self, linear, angular):
        sequence = self.queue.submit(linear, angular)

        if sequence is None:
            raise RuntimeError("Command queue rejected command")

        return sequence
