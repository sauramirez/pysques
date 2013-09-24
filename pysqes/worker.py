import pickle
import signal
import time

from .task import BasePySQS


class SQSWorker(BasePySQS):
    """
    Workers are in charge of fetching new jobs from SQS and then executes them
    if there are any.
    """
    _shutdown = False
    # the backend should speciy a store_result method
    backend = None

    def __init__(self, *args, **kwargs):
        backend = kwargs.pop('backend', None)
        self.backend = backend
        super(SQSWorker, self).__init__(*args, **kwargs)

    def register_signal_handlers(self):
        """
        Register our handlers so that we can stop the process from running
        """
        signal.signal(signal.SIGTERM, self._shutdown_signal)
        signal.signal(signal.SIGINT, self._shutdown_signal)
        signal.signal(signal.SIGQUIT, self._shutdown_signal)
        signal.signal(signal.SIGUSR1, self._shutdown_signal)

    def shutdown(self):
        self._shutdown = True

    def _shutdown_signal(self, signum, frame):
        self.shutdown()

    def work(self, thread=False):
        """
        This is the method in charge of fetching the jobs from SQS
        """
        if not thread:
            self.register_signal_handlers()

        # start running our worker
        while True:
            messages = self.queue.get_messages()
            for message in messages:
                task = message.get_body()
                task = pickle.loads(task)
                task_id = task['task_id']
                task_name = task['name']
                success = False
                tries = 0
                while not success and tries < 3:
                    try:
                        result = task['fun'](*task['args'], **task['kwargs'])
                        success = True
                    except Exception, e:
                        result = e
                    tries += 1

                self.queue.delete_message(message)

                # if a backend has been specified then we can run a save
                # method on it
                if self.backend:
                    self.backend.store_result(success, result, task_id, task_name)

            # if no messages received then we can just sleep for a while
            if len(messages) == 0:
                time.sleep(1)

            if self._shutdown:
                break

    @classmethod
    def run(cls, queue, timeout):
        worker = cls(queue, timeout)
        worker.work()
